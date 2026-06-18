import html
import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any
from typing import Dict
from typing import List
from urllib.parse import parse_qs
from urllib.parse import urlparse

import gradio as gr
import qrcode
import requests
import util
from loguru import logger

from interface.common import _format_sale_status
from interface.project import fetch_project_payload
from util import ConfigDB
from util import GLOBAL_COOKIE_PATH
from util import TEMP_PATH
from util import set_main_request
from util.request.BiliRequest import BiliRequest
from util.request.CookieManager import parse_cookie_list

buyer_value: List[Dict[str, Any]] = []
addr_value: List[Dict[str, Any]] = []
ticket_value: List[Dict[str, Any]] = []
project_name: str = ""
ticket_str_list: List[str] = []
sales_dates: list[str] = []
project_id = 0
is_hot_project = False


def _read_positive_int(value) -> int | None:
    if value is None:
        return None
    try:
        num = int(value)
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def _iter_project_dates(start_ts: int, end_ts: int):
    start_day = datetime.fromtimestamp(start_ts).date()
    end_day = datetime.fromtimestamp(end_ts).date()
    cursor = start_day
    while cursor <= end_day:
        yield cursor.strftime("%Y-%m-%d")
        cursor += timedelta(days=1)


def _fetch_screens_by_date(
    request: BiliRequest, project_id: int, date_str: str
) -> list[dict]:
    response = request.get(
        url=f"https://show.bilibili.com/api/ticket/project/infoByDate?id={project_id}&date={date_str}",
    )
    payload = response.json()
    errno = payload.get("errno", payload.get("code"))
    if errno != 0:
        raise RuntimeError(payload.get("msg", payload.get("message", "unknown error")))

    data = payload.get("data") if isinstance(payload, dict) else None
    screens = data.get("screen_list") if isinstance(data, dict) else None
    return screens if isinstance(screens, list) else []


def _normalize_date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = int(value)
        if timestamp > 10**12:
            timestamp //= 1000
        try:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    match = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _screen_matches_date(screen: dict[str, Any], date_str: str) -> bool:
    candidates = [
        screen.get("start_time"),
        screen.get("start_time_str"),
        screen.get("name"),
    ]
    for ticket in screen.get("ticket_list", []):
        if isinstance(ticket, dict):
            candidates.append(ticket.get("screen_name"))

    return any(
        _normalize_date_string(candidate) == date_str for candidate in candidates
    )


def _fetch_screens_by_date_with_fallback(
    request: BiliRequest, project_id: int, date_str: str
) -> list[dict]:
    screens = _fetch_screens_by_date(request, project_id, date_str)
    if screens:
        return screens

    project_payload = fetch_project_payload(request=request, project_id=project_id)
    fallback_screens: list[dict] = []
    for screen in project_payload.get("screen_list", []):
        if not isinstance(screen, dict):
            continue
        if not _screen_matches_date(screen, date_str):
            continue
        screen["project_id"] = screen.get("project_id", project_id)
        fallback_screens.append(screen)
    return fallback_screens


def _merge_screens(base_screens: list[dict], extra_screens: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen_screen_ids: set[int] = set()

    for screen in [*base_screens, *extra_screens]:
        if not isinstance(screen, dict):
            continue
        sid = _read_positive_int(screen.get("id"))
        if sid is None or sid in seen_screen_ids:
            continue
        seen_screen_ids.add(sid)
        merged.append(screen)

    return merged


def filename_filter(filename):
    return re.sub(r'[/:*?"<>|]', "", filename)


def _format_price(price: int | float) -> str:
    return f"￥{price / 100:.2f}".rstrip("0").rstrip(".")


def _render_ticket_info_html(
    title: str,
    lines: list[tuple[str, str]],
    badge: str | None = None,
    hint: str | None = None,
) -> str:
    items_html = "".join(
        (
            '<div class="btb-mini-card">'
            f"<strong>{html.escape(label)}</strong>"
            f"<span>{html.escape(value)}</span>"
            "</div>"
        )
        for label, value in lines
    )
    return f"""
    <div class="btb-ticket-panel">
        <div class="btb-mini-grid">{items_html}</div>
    </div>
    """


def _empty_ticket_info_updates():
    return [
        gr.update(choices=[], value=None),
        gr.update(choices=[], value=[]),
        gr.update(choices=[], value=None),
        gr.update(visible=False),
        gr.update(value="", visible=False),
        gr.update(visible=False, value=None),
    ]


def _format_ticket_option(screen_name: str, ticket: dict, ticket_price: int) -> str:
    ticket_desc = ticket.get("desc", "")
    sale_start = str(ticket.get("sale_start", "未知"))
    return (
        f"{screen_name} - {ticket_desc} - {_format_price(ticket_price)} - "
        f"{_format_sale_status(ticket)} - 【起售时间：{sale_start}】"
    )


def _resolve_project_input(project_input: Any) -> tuple[int, int | str, str]:
    if isinstance(project_input, int):
        return project_input, project_input, ""

    text = str(project_input)
    stripped = text.strip()
    if not stripped:
        raise gr.Error("请输入活动详情页链接")

    if stripped.lower().isdigit():
        return (
            int(stripped),
            text,
            f"当前票务id为 {text}",
        )

    if "http" in stripped or "https" in stripped:
        extracted_id = extract_id_from_url(stripped)
        if extracted_id is None:
            raise gr.Error("无法从链接中识别票务 ID，请确认链接是会员购活动详情页。")
        return (
            int(extracted_id),
            int(extracted_id),
            f"已从链接中提取项目 ID：{extracted_id}",
        )

    if stripped.isdigit():
        parsed_id = int(stripped)
        return parsed_id, parsed_id, ""

    raise gr.Error("请输入活动详情页链接，或直接输入纯数字票务 ID。")


def on_submit_ticket_id(num):
    global buyer_value
    global addr_value
    global ticket_value
    global project_name
    global ticket_str_list
    global sales_dates
    global project_id
    global is_hot_project
    try:
        buyer_value = []
        addr_value = []
        ticket_value = []
        _, num, extracted_id_message = _resolve_project_input(num)

        try:
            data = fetch_project_payload(request=util.main_request, project_id=num)
        except Exception as exc:
            raise gr.Error(
                str(exc) or "票务信息返回异常，当前活动页暂时不可用。"
            ) from exc

        ticket_str_list = []
        project_id = data["id"]
        project_name = data["name"]
        is_hot_project = data["hotProject"]
        sales_dates = [t["date"] for t in data["sales_dates"]]
        sales_dates_show = len(data["sales_dates"]) != 0
        for item in data["screen_list"]:
            item["project_id"] = data["id"]

        daily_screens: list[dict] = []
        for date_str in _iter_project_dates(data["start_time"], data["end_time"]):
            try:
                items = _fetch_screens_by_date_with_fallback(
                    util.main_request, project_id, date_str
                )
            except Exception:
                continue
            for item in items:
                if isinstance(item, dict):
                    item["project_id"] = data["id"]
                    daily_screens.append(item)

        data["screen_list"] = _merge_screens(data["screen_list"], daily_screens)

        try:
            good_list = util.main_request.get(
                url=f"https://show.bilibili.com/api/ticket/linkgoods/list?project_id={project_id}&page_type=0"
            ).json()
            ids = [item["id"] for item in good_list["data"]["list"]]
            for item_id in ids:
                good_detail = util.main_request.get(
                    url=f"https://show.bilibili.com/api/ticket/linkgoods/detail?link_id={item_id}"
                ).json()
                for item in good_detail["data"]["specs_list"]:
                    item["project_id"] = good_detail["data"]["item_id"]
                    item["link_id"] = item_id
                data["screen_list"] += good_detail["data"]["specs_list"]
        except Exception as exc:
            logger.warning(f"获取周边商品信息失败: {exc}")

        for screen in data["screen_list"]:
            if "name" not in screen:
                continue
            screen_name = screen["name"]
            screen_id = screen["id"]
            current_project_id = screen["project_id"]
            express_fee = (
                0
                if data["has_eticket"]
                else max(int(screen.get("express_fee", 0) or 0), 0)
            )

            for ticket in screen["ticket_list"]:
                ticket_price = int(ticket.get("price", 0)) + express_fee
                ticket["price"] = ticket_price
                ticket["screen"] = screen_name
                ticket["screen_id"] = screen_id
                ticket["is_hot_project"] = is_hot_project
                if "link_id" in screen:
                    ticket["link_id"] = screen["link_id"]
                ticket_str_list.append(
                    _format_ticket_option(screen_name, ticket, ticket_price)
                )
                ticket_value.append(
                    {"project_id": current_project_id, "ticket": ticket}
                )

        buyer_json = util.main_request.get(
            url=f"https://show.bilibili.com/api/ticket/buyer/list?is_default&projectId={project_id}"
        ).json()
        addr_json = util.main_request.get(
            url="https://show.bilibili.com/api/ticket/addr/list"
        ).json()
        buyer_value = buyer_json["data"]["list"]
        buyer_str_list = [
            f"{item['name']}-{item['personal_id']}" for item in buyer_value
        ]
        addr_value = addr_json["data"]["addr_list"]
        addr_str_list = [
            f"{item['addr']}-{item['name']}-{item['phone']}" for item in addr_value
        ]

        yield [
            gr.update(choices=ticket_str_list),
            gr.update(choices=buyer_str_list),
            gr.update(choices=addr_str_list),
            gr.update(visible=True),
            gr.update(
                value=_render_ticket_info_html(
                    title="票务信息",
                    badge="已获取",
                    lines=[
                        ("票务 ID", str(num)),
                        ("展会名称", project_name),
                    ],
                    hint=extracted_id_message or "请继续选择票档、购票人和地址。",
                ),
                visible=True,
            ),
            gr.update(choices=sales_dates, visible=True, value=sales_dates[0])
            if sales_dates_show
            else gr.update(choices=[], visible=False, value=None),
        ]
    except gr.Error as exc:
        gr.Warning(exc.message)
        yield _empty_ticket_info_updates()
    except Exception as exc:
        logger.exception(exc)
        gr.Warning("获取票务信息失败，请确认活动链接是否正确，或稍后重试。")
        yield _empty_ticket_info_updates()


def extract_id_from_url(url):
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    ticket_id = query_params.get("id", [None])[0]
    if isinstance(ticket_id, str) and ticket_id.isdigit():
        return ticket_id
    return None


def on_submit_all(
    ticket_id,
    ticket_info: int,
    people_indices,
    people_buyer_name,
    people_buyer_phone,
    address_index,
):
    try:
        if ticket_id is None:
            raise gr.Error("请输入正确的活动链接。")
        if len(people_indices) == 0:
            raise gr.Error("请至少选择一位实名购票人。")
        if addr_value is None:
            raise gr.Error("没有可用的收货地址。")
        if ticket_info is None:
            raise gr.Error("请先选择票档。")
        if not people_buyer_name:
            raise gr.Error("请填写联系人姓名。")
        if not people_buyer_phone:
            raise gr.Error("请填写联系人电话。")
        if address_index is None:
            raise gr.Error("请先选择收货地址。")

        ticket_cur: dict[str, Any] = ticket_value[ticket_info]
        people_cur = [buyer_value[item] for item in people_indices]
        resolved_project_id, config_project_id, _message = _resolve_project_input(
            ticket_id
        )

        ConfigDB.insert("people_buyer_name", people_buyer_name)
        ConfigDB.insert("people_buyer_phone", people_buyer_phone)

        address_cur = addr_value[address_index]
        username = util.main_request.get_request_name()
        detail = f"{username}-{project_name}-{ticket_str_list[ticket_info]}"
        for person in people_cur:
            detail += f"-{person['name']}"

        selected_project_id = ticket_cur["project_id"]
        if selected_project_id == resolved_project_id:
            selected_project_id = config_project_id

        config_dir = {
            "username": username,
            "detail": detail,
            "count": len(people_indices),
            "screen_id": ticket_cur["ticket"]["screen_id"],
            "project_id": selected_project_id,
            "is_hot_project": ticket_cur["ticket"]["is_hot_project"],
            "sku_id": ticket_cur["ticket"]["id"],
            "sale_start": ticket_cur["ticket"].get("sale_start", ""),
            "order_type": 1,
            "pay_money": ticket_cur["ticket"]["price"] * len(people_indices),
            "buyer_info": people_cur,
            "buyer": people_buyer_name,
            "tel": people_buyer_phone,
            "deliver_info": {
                "name": address_cur["name"],
                "tel": address_cur["phone"],
                "addr_id": address_cur["id"],
                "addr": address_cur["prov"]
                + address_cur["city"]
                + address_cur["area"]
                + address_cur["addr"],
            },
            "cookies": util.main_request.cookieManager.get_cookies(),
            "phone": util.main_request.cookieManager.get_config_value("phone", ""),
        }
        if "link_id" in ticket_cur["ticket"]:
            config_dir["link_id"] = ticket_cur["ticket"]["link_id"]

        filename = os.path.join(TEMP_PATH, filename_filter(detail) + ".json")
        with open(filename, "w", encoding="utf-8") as handle:
            json.dump(config_dir, handle, ensure_ascii=False, indent=4)

        yield [
            gr.update(value=config_dir, visible=True),
            gr.update(value=filename, visible=True),
        ]
    except gr.Error as exc:
        gr.Warning(exc.message)
    except Exception:
        raise gr.Error("生成配置失败，请检查是否有遗漏的必填项。")


def upload_file(filepath):
    """导入 cookie 文件并添加到账号池"""
    try:
        temp_request = BiliRequest(cookies_config_path=filepath)
        cookies = temp_request.cookieManager.get_cookies()
        account = util.main_request.cookieManager.add_account(cookies)
        set_main_request(BiliRequest(cookies_config_path=GLOBAL_COOKIE_PATH))
        util.main_request.cookieManager.db.insert("cookie", account.cookies)
        gr.Info(f"已导入账号 {account.name}", duration=5)

        new_choices = [
            f"{a.uid} - {a.name} (Lv{a.level})"
            for a in util.main_request.cookieManager.get_accounts()
        ]
        yield [
            gr.update(value=GLOBAL_COOKIE_PATH),
            gr.update(
                choices=new_choices,
                value=new_choices[-1] if new_choices else None,
            ),
        ]
    except Exception as exc:
        logger.exception(exc)
        raise gr.Error("登录信息导入失败，请检查文件格式。")


def login_tab():
    with gr.Column(elem_classes="btb-page-section"):
        with gr.Accordion(
            label="填写当前账号绑定的手机号（可选）",
            open=False,
            elem_classes="btb-card btb-soft-accordion",
        ):
            phone_gate_ui = gr.Textbox(
                label="手机号",
                info="手机验证出现概率较低，可以留空",
                value=util.main_request.cookieManager.get_config_value("phone", ""),
            )

            def input_phone(_phone):
                util.main_request.cookieManager.set_config_value("phone", _phone)

            phone_gate_ui.change(fn=input_phone, inputs=phone_gate_ui, outputs=None)

        def generate_qrcode():
            headers = {
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
                ),
            }
            for _ in range(10):
                res = requests.get(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                    headers=headers,
                    timeout=10,
                )
                res_json = res.json()
                if res_json["code"] == 0:
                    url = res_json["data"]["url"]
                    qrcode_key = res_json["data"]["qrcode_key"]
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_H,  # type: ignore
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(url)
                    qr.make(fit=True)
                    path = os.path.join(TEMP_PATH, f"login_qrcode_{qrcode_key}.png")
                    qr.make_image(
                        fill_color="black", back_color="white"
                    ).get_image().save(path)
                    return path, qrcode_key
                time.sleep(1)
            return None, "二维码生成失败"

        def poll_login(qrcode_key):
            headers = {"User-Agent": "Mozilla/5.0"}
            for _ in range(120):
                res = requests.get(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                    params={"qrcode_key": qrcode_key},
                    headers=headers,
                    timeout=5,
                )
                poll_res = res.json()
                if poll_res.get("code") != 0:
                    time.sleep(0.5)
                    continue

                code = poll_res["data"]["code"]
                if code == 0:
                    cookies = parse_cookie_list(res.headers["set-cookie"])
                    return "登录成功", cookies
                if code in (86101, 86090):
                    time.sleep(0.5)
                    continue
                return f"扫码失败：{poll_res['data']['message']}", None

            return "登录超时，请重试。", None

        def start_login():
            img_path, qrcode_key = generate_qrcode()
            if not img_path:
                return None, "二维码生成失败"
            return img_path, qrcode_key

        qrcode_key_state = gr.State("")

        def _get_account_choices():
            accounts = util.main_request.cookieManager.get_accounts()
            return [f"{a.uid} - {a.name} (Lv{a.level})" for a in accounts]

        def _get_default_account_choice() -> str | None:
            return _get_default_account_choice_from(_get_account_choices())

        def _get_default_account_choice_from(choices: list[str]) -> str | None:
            if not choices:
                return None

            active_uid = util.main_request.cookieManager.get_cookies_value("DedeUserID")
            if active_uid is not None:
                active_uid = str(active_uid)
                for choice in choices:
                    if _find_uid_from_choice(choice) == active_uid:
                        return choice

            return choices[0]

        def _find_uid_from_choice(choice: str) -> str:
            if not choice:
                return ""
            return choice.split(" - ")[0] if " - " in choice else choice

        def _activate_account(account) -> None:
            set_main_request(BiliRequest(cookies_config_path=GLOBAL_COOKIE_PATH))
            util.main_request.cookieManager.db.insert("cookie", account.cookies)
            name = util.main_request.get_request_name()
            if name == "未登录":
                gr.Warning(
                    f"账号 {account.name} 的 cookies 可能已过期，请重新扫码登录",
                    duration=5,
                )

        with gr.Row(elem_classes="btb-split-grid !items-stretch"):
            with gr.Column(elem_classes="btb-subcard", scale=4):
                qr_img = gr.Image(
                    label="扫我",
                    visible=False,
                    elem_classes="btb-qr-preview",
                )
                login_btn = gr.Button(
                    "点击生成登录二维码",
                    elem_classes="btb-strong-button",
                )
                check_btn = gr.Button(
                    "扫码后点击确认登录",
                    visible=False,
                    elem_classes="btb-soft-button",
                )

            with gr.Column(elem_classes="btb-subcard", scale=6):
                gr.HTML(
                    """
                    <div class="btb-inline-panel">
                        <h4>账号管理</h4>
                    </div>
                    """
                )
                account_choices = _get_account_choices()
                account_dropdown = gr.Dropdown(
                    label="当前账号",
                    choices=account_choices,
                    value=_get_default_account_choice_from(account_choices),
                    interactive=True,
                    allow_custom_value=False,
                    filterable=False,
                )
                with gr.Row(elem_classes="!gap-2"):
                    delete_btn = gr.Button(
                        "删除当前账号",
                        elem_classes="btb-soft-button",
                        variant="stop",
                    )
                    upload_ui = gr.UploadButton(
                        label="导入现有登录文件",
                        elem_classes="btb-soft-button",
                    )
                gr_file_ui = gr.File(
                    label="当前登录信息文件",
                    value=lambda: GLOBAL_COOKIE_PATH,
                )

        def on_login_click():
            img_path, msg_or_key = start_login()
            if img_path:
                gr.Info("已生成二维码，请用 B 站客户端扫码", duration=5)
                return [
                    gr.update(value=img_path, visible=True),
                    msg_or_key,
                ]
            gr.Warning("生成二维码失败", duration=5)
            return [
                gr.update(value="", visible=False),
                "",
            ]

        def on_check_login(key):
            if not key:
                return [
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                ]
            msg, cookies = poll_login(key)
            if cookies:
                try:
                    account = util.main_request.cookieManager.add_account(cookies)
                    _activate_account(account)
                    gr.Info(f"已添加并切换至账号 {account.name}", duration=5)
                    new_choices = _get_account_choices()
                    return [
                        gr.update(value=GLOBAL_COOKIE_PATH),
                        gr.update(visible=False),
                        gr.update(visible=False),
                        gr.update(
                            choices=new_choices,
                            value=_get_default_account_choice_from(new_choices),
                        ),
                        gr.update(value=""),
                    ]
                except Exception as exc:
                    logger.exception(exc)
                    gr.Warning(f"添加账号失败: {exc}", duration=5)

            gr.Warning(msg, duration=5)
            return [
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
            ]

        def on_dropdown_change(choice):
            uid = _find_uid_from_choice(choice)
            if not uid:
                return [gr.update(), gr.update()]
            account = util.main_request.cookieManager.find_by_uid(uid)
            if account is None:
                gr.Warning(f"未找到账号 {uid}", duration=5)
                return [gr.update(), gr.update()]
            _activate_account(account)
            gr.Info(f"已切换到账号 {account.name}", duration=5)
            return [
                gr.update(value=GLOBAL_COOKIE_PATH),
                gr.update(),
            ]

        def on_delete_account(choice):
            uid = _find_uid_from_choice(choice)
            if not uid:
                gr.Warning("请先选择一个账号", duration=5)
                return [gr.update(), gr.update(), gr.update()]
            account = util.main_request.cookieManager.find_by_uid(uid)
            util.main_request.cookieManager.remove_account(uid)
            new_choices = _get_account_choices()

            current_name = util.main_request.get_request_name()
            was_active = account and (
                account.name == current_name or current_name == "未登录"
            )

            if was_active and new_choices:
                first_account = util.main_request.cookieManager.get_accounts()[0]
                _activate_account(first_account)
                gr.Info(
                    f"已删除账号 {account.name if account else uid}，自动切换到 {first_account.name}",
                    duration=5,
                )
                return [
                    gr.update(value=GLOBAL_COOKIE_PATH),
                    gr.update(choices=new_choices, value=new_choices[0]),
                    gr.update(),
                ]
            if was_active:
                set_main_request(BiliRequest(cookies_config_path=GLOBAL_COOKIE_PATH))
                util.main_request.cookieManager.db.delete("cookie")
                gr.Info(
                    f"已删除最后一个账号 {account.name if account else uid}，当前无活跃账号",
                    duration=5,
                )
                return [
                    gr.update(value=GLOBAL_COOKIE_PATH),
                    gr.update(choices=new_choices, value=None),
                    gr.update(),
                ]

            gr.Info(f"已删除账号 {account.name if account else uid}", duration=5)
            return [
                gr.update(),
                gr.update(
                    choices=new_choices,
                    value=_get_default_account_choice_from(new_choices),
                ),
                gr.update(),
            ]

        login_btn.click(on_login_click, outputs=[qr_img, qrcode_key_state])

        @gr.on(qrcode_key_state.change, inputs=qrcode_key_state, outputs=check_btn)
        def qrcode_key_state_change(key):
            return gr.update(visible=bool(key))

        check_btn.click(
            on_check_login,
            inputs=[qrcode_key_state],
            outputs=[
                gr_file_ui,
                qr_img,
                check_btn,
                account_dropdown,
                qrcode_key_state,
            ],
        )
        account_dropdown.change(
            on_dropdown_change,
            inputs=[account_dropdown],
            outputs=[gr_file_ui, account_dropdown],
        )
        delete_btn.click(
            on_delete_account,
            inputs=[account_dropdown],
            outputs=[gr_file_ui, account_dropdown, qr_img],
        )
        upload_ui.upload(upload_file, [upload_ui], [gr_file_ui, account_dropdown])


def setting_tab():
    with gr.Column(elem_classes="btb-page-section"):
        with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card"):
            gr.HTML(
                """
                <div class="btb-card-head">
                    <div>
                        <h3>票务配置</h3>
                        <p>输入活动链接获取票档，然后依次完成联系人、地址和实名购票人配置。</p>
                    </div>
                </div>
                """
            )
            with gr.Row(elem_classes="btb-action-band !items-end"):
                ticket_id_ui = gr.Textbox(
                    label="想抢票的活动链接",
                    interactive=True,
                    placeholder="https://show.bilibili.com/platform/detail.html?id=xxxx",
                    scale=5,
                )
                ticket_id_btn = gr.Button(
                    "获取票务信息",
                    elem_classes="btb-strong-button",
                    scale=1,
                )

            info_ui = gr.HTML(visible=False, elem_classes="btb-ticket-summary")

            with gr.Column(
                visible=False, elem_id="ticket-detail", elem_classes="btb-detail-shell"
            ) as inner:
                with gr.Row():
                    ticket_info_ui = gr.Dropdown(
                        label="选择票档",
                        interactive=True,
                        type="index",
                        allow_custom_value=False,
                        filterable=False,
                    )
                    date_ui = gr.Dropdown(
                        label="选择日期",
                        choices=[],
                        interactive=True,
                        allow_custom_value=False,
                        filterable=False,
                    )

                with gr.Row(elem_classes="btb-split-grid !items-end"):
                    people_buyer_name = gr.Textbox(
                        value=lambda: ConfigDB.get("people_buyer_name") or "",
                        label="联系人姓名",
                        placeholder="请输入姓名",
                        interactive=True,
                    )
                    people_buyer_phone = gr.Textbox(
                        value=lambda: ConfigDB.get("people_buyer_phone") or "",
                        label="联系人电话",
                        placeholder="请输入电话",
                        interactive=True,
                    )
                    address_ui = gr.Dropdown(
                        label="收货地址",
                        interactive=True,
                        type="index",
                        info="请提前在b站手机端填写地址",
                        allow_custom_value=False,
                        filterable=False,
                    )

                people_ui = gr.CheckboxGroup(
                    label="实名购票人",
                    interactive=True,
                    type="index",
                    info="选中几位购票人，就相当于购买几张票。",
                    elem_classes="btb-people-grid",
                )

                with gr.Row(elem_classes="btb-output-band !items-start"):
                    config_btn = gr.Button(
                        "生成配置",
                        elem_classes="btb-strong-button",
                        scale=0,
                    )
                    config_file_ui = gr.File(visible=False, scale=1)

                config_output_ui = gr.JSON(label="生成结果", visible=False)

                config_btn.click(
                    fn=on_submit_all,
                    inputs=[
                        ticket_id_ui,
                        ticket_info_ui,
                        people_ui,
                        people_buyer_name,
                        people_buyer_phone,
                        address_ui,
                    ],
                    outputs=[config_output_ui, config_file_ui],
                )

            ticket_id_btn.click(
                fn=on_submit_ticket_id,
                inputs=ticket_id_ui,
                outputs=[
                    ticket_info_ui,
                    people_ui,
                    address_ui,
                    inner,
                    info_ui,
                    date_ui,
                ],
                show_progress="hidden",
            )

            def on_submit_data(_date):
                global ticket_str_list
                global ticket_value
                global is_hot_project
                global project_id
                global project_name

                try:
                    screens = _fetch_screens_by_date_with_fallback(
                        util.main_request, project_id, _date
                    )

                    if not screens:
                        gr.Warning("该日期暂无票务信息。")
                        return [
                            gr.update(choices=sales_dates, value=_date, visible=True),
                            gr.update(choices=[]),
                            gr.update(value="", visible=False),
                        ]

                    ticket_str_list = []
                    ticket_value = []

                    for screen in screens:
                        screen_name = screen["name"]
                        screen_id = screen["id"]
                        express_fee = max(int(screen.get("express_fee", 0) or 0), 0)
                        for ticket in screen["ticket_list"]:
                            ticket_price = int(ticket["price"]) + express_fee
                            ticket["price"] = ticket_price
                            ticket["screen"] = screen_name
                            ticket["screen_id"] = screen_id
                            ticket["is_hot_project"] = is_hot_project
                            ticket_str_list.append(
                                _format_ticket_option(
                                    screen_name,
                                    ticket,
                                    ticket_price,
                                )
                            )
                            ticket_value.append(
                                {"project_id": project_id, "ticket": ticket}
                            )

                    return [
                        gr.update(choices=sales_dates, value=_date, visible=True),
                        gr.update(choices=ticket_str_list),
                        gr.update(
                            value=_render_ticket_info_html(
                                title="票务信息",
                                badge="日期已更新",
                                lines=[
                                    ("票务 ID", str(project_id)),
                                    ("展会名称", project_name),
                                ],
                                hint="票档列表已按当前日期刷新，请重新确认起售时间。",
                            ),
                            visible=True,
                        ),
                    ]
                except Exception as exc:
                    logger.exception(exc)
                    return [
                        gr.update(),
                        gr.update(),
                        gr.update(value="", visible=False),
                    ]

            date_ui.change(
                fn=on_submit_data,
                inputs=date_ui,
                outputs=[date_ui, ticket_info_ui, info_ui],
            )
