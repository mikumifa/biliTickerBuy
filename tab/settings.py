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
from gradio_calendar import Calendar
from loguru import logger

from util import ConfigDB
from util import GLOBAL_COOKIE_PATH
from util import TEMP_PATH
from util import set_main_request
from util.BiliRequest import BiliRequest
from util.CookieManager import parse_cookie_list

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
        url=f"https://show.bilibili.com/api/ticket/project/infoByDate?id={project_id}&date={date_str}"
    )
    payload = response.json()
    errno = payload.get("errno", payload.get("code"))
    if errno != 0:
        raise RuntimeError(payload.get("msg", payload.get("message", "unknown error")))

    data = payload.get("data") if isinstance(payload, dict) else None
    screens = data.get("screen_list") if isinstance(data, dict) else None
    return screens if isinstance(screens, list) else []


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


sales_flag_number_map = {
    1: "不可售",
    2: "预售",
    3: "停售",
    4: "售罄",
    5: "不可用",
    6: "库存紧张",
    8: "暂时售罄",
    9: "不在白名单",
    101: "未开始",
    102: "已结束",
    103: "未完成",
    105: "已下架",
    106: "已取消",
}


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
    badge_html = (
        f'<span class="btb-badge-pink">{html.escape(badge)}</span>' if badge else ""
    )
    items_html = "".join(
        (
            '<div class="btb-mini-card">'
            f"<strong>{html.escape(label)}</strong>"
            f"<span>{html.escape(value)}</span>"
            "</div>"
        )
        for label, value in lines
    )
    hint_html = (
        f'<p class="btb-card-note">{html.escape(hint)}</p>'
        if hint
        else ""
    )
    return f"""
    <div class="btb-ticket-panel">
        <div class="btb-ticket-panel__head">
            <div>
                <div class="btb-card-head__eyebrow">Ticket Snapshot</div>
                <h4>{html.escape(title)}</h4>
            </div>
            {badge_html}
        </div>
        <div class="btb-mini-grid">{items_html}</div>
        {hint_html}
    </div>
    """


def _render_setting_steps(current: str, *, logged_in: bool = False, configured: bool = False) -> str:
    login_done = logged_in
    config_done = configured
    export_done = configured

    def step(label: str, number: int, key: str, done: bool) -> str:
        classes = ["btb-step-strip__item"]
        if key == current and not done:
            classes.append("is-active")
        if done:
            classes.append("is-done")
        return (
            f'<div class="{" ".join(classes)}">'
            f"<span>{number}</span>"
            f"<strong>{label}</strong>"
            "</div>"
        )

    return f"""
    <div class="btb-step-strip">
        {step("登录", 1, "login", login_done)}
        {step("票务配置", 2, "ticket", config_done)}
        {step("导出配置", 3, "export", export_done)}
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
        gr.update(value=_render_setting_steps("ticket", logged_in=True, configured=False)),
    ]


def _format_ticket_option(screen_name: str, ticket: dict, express_fee: int) -> str:
    ticket_desc = ticket.get("desc", "")
    sale_start = str(ticket.get("sale_start", "未知"))
    ticket_price = int(ticket.get("price", 0)) + express_fee
    ticket_can_buy = sales_flag_number_map.get(ticket.get("sale_flag_number"), "未知")
    return (
        f"{screen_name} - {ticket_desc} - {_format_price(ticket_price)} - "
        f"{ticket_can_buy} - 【起售时间：{sale_start}】"
    )


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
        extracted_id_message = ""

        if isinstance(num, str) and ("http" in num or "https" in num):
            num = extract_id_from_url(num)
            if num is None:
                raise gr.Error(
                    "无法从链接中识别票务 ID，请确认链接是会员购活动详情页。"
                )
            extracted_id_message = f"已从链接中提取项目 ID：{num}"
        elif isinstance(num, str) and num.isdigit():
            num = int(num)
        else:
            raise gr.Error("请输入活动详情页链接，或直接输入纯数字票务 ID。")

        res = util.main_request.get(
            url=f"https://show.bilibili.com/api/ticket/project/getV2?version=134&id={num}&project_id={num}"
        )
        ret = res.json()

        if ret.get("errno", ret.get("code")) == 100001:
            raise gr.Error("没有找到对应票务，请检查链接或票务 ID 是否正确。")
        if ret.get("errno", ret.get("code")) != 0:
            raise gr.Error(ret.get("msg", ret.get("message", "未知错误")))

        data = ret.get("data")
        if not isinstance(data, dict):
            raise gr.Error("票务信息返回异常，当前活动页暂时不可用。")

        ticket_str_list = []
        project_id = data["id"]
        project_name = data["name"]
        is_hot_project = data["hotProject"]

        project_start_time = datetime.fromtimestamp(data["start_time"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        project_end_time = datetime.fromtimestamp(data["end_time"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        venue_info = data["venue_info"]
        venue_name = venue_info["name"]
        venue_address = venue_info["address_detail"]
        sales_dates = [t["date"] for t in data["sales_dates"]]
        sales_dates_show = len(data["sales_dates"]) != 0
        for item in data["screen_list"]:
            item["project_id"] = data["id"]

        daily_screens: list[dict] = []
        for date_str in _iter_project_dates(data["start_time"], data["end_time"]):
            try:
                items = _fetch_screens_by_date(util.main_request, project_id, date_str)
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
            express_fee = 0 if data["has_eticket"] else max(screen.get("express_fee", 0), 0)

            for ticket in screen["ticket_list"]:
                ticket["price"] = int(ticket.get("price", 0)) + express_fee
                ticket["screen"] = screen_name
                ticket["screen_id"] = screen_id
                ticket["is_hot_project"] = is_hot_project
                if "link_id" in screen:
                    ticket["link_id"] = screen["link_id"]
                ticket_str_list.append(_format_ticket_option(screen_name, ticket, express_fee))
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
        buyer_str_list = [f"{item['name']}-{item['personal_id']}" for item in buyer_value]
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
                        ("活动时间", f"{project_start_time} - {project_end_time}"),
                        ("场馆地址", f"{venue_name} {venue_address}"),
                    ],
                    hint=extracted_id_message or "请继续选择票档、购票人和地址。",
                ),
                visible=True,
            ),
            gr.update(visible=True, value=sales_dates[0])
            if sales_dates_show
            else gr.update(visible=False),
            gr.update(value=_render_setting_steps("ticket", logged_in=True, configured=False)),
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
        ticket_id = extract_id_from_url(ticket_id)
        if ticket_id is None:
            raise gr.Error("未能从当前链接中解析出票务 ID，请重新获取票务信息。")

        ConfigDB.insert("people_buyer_name", people_buyer_name)
        ConfigDB.insert("people_buyer_phone", people_buyer_phone)

        address_cur = addr_value[address_index]
        username = util.main_request.get_request_name()
        detail = f"{username}-{project_name}-{ticket_str_list[ticket_info]}"
        for person in people_cur:
            detail += f"-{person['name']}"

        config_dir = {
            "username": username,
            "detail": detail,
            "count": len(people_indices),
            "screen_id": ticket_cur["ticket"]["screen_id"],
            "project_id": ticket_cur["project_id"],
            "is_hot_project": ticket_cur["ticket"]["is_hot_project"],
            "sku_id": ticket_cur["ticket"]["id"],
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
            gr.update(value=_render_setting_steps("export", logged_in=True, configured=True)),
        ]
    except gr.Error as exc:
        gr.Warning(exc.message)
    except Exception:
        raise gr.Error("生成配置失败，请检查是否有遗漏的必填项。")


def upload_file(filepath):
    try:
        set_main_request(BiliRequest(cookies_config_path=filepath))
        name = util.main_request.get_request_name()
        gr.Info("导入成功", duration=5)
        yield [
            gr.update(value=name),
            gr.update(value=ConfigDB.get("cookies_path")),
            gr.update(value=_render_setting_steps("ticket", logged_in=True, configured=False)),
        ]
    except Exception as exc:
        name = util.main_request.get_request_name()
        logger.exception(exc)
        raise gr.Error("登录信息导入失败，请检查文件格式。")


def setting_tab():
    with gr.Column(elem_classes="btb-page-section"):
        gr.HTML(
            """
            <section class="btb-section-head">
                <div>
                    <div class="btb-section-head__eyebrow">STEP 01</div>
                    <h2>生成抢票配置</h2>
                    <p>先完成账号授权，再补齐联系人、票务和配送信息，最后导出配置文件。</p>
                </div>
            </section>
            """
        )
        step_status_ui = gr.HTML(
            value=_render_setting_steps("login", logged_in=False, configured=False)
        )

        gr.HTML(
            """
            <div class="btb-card btb-card-amber">
                <div class="btb-card-head">
                    <div>
                        <div class="btb-card-head__eyebrow">Before You Start</div>
                        <h3>使用前必读</h3>
                        <p>请先在会员购中心补齐基础资料，否则生成配置时可能没有可选项。</p>
                    </div>
                    <span class="btb-badge-amber">准备检查</span>
                </div>
                <div class="btb-mini-grid">
                    <div class="btb-mini-card">
                        <strong>收货地址</strong>
                        <span>会员购中心 → 地址管理</span>
                    </div>
                    <div class="btb-mini-card">
                        <strong>购票人信息</strong>
                        <span>会员购中心 → 购票人信息</span>
                    </div>
                </div>
                <p class="btb-card-note">建议提前补齐资料，避免开抢前还要回到会员购手动修改。</p>
            </div>
            """
        )

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
                    path = os.path.join(TEMP_PATH, "login_qrcode.png")
                    qr.make_image(fill_color="black", back_color="white").get_image().save(path)
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

        with gr.Column(elem_classes="btb-card btb-card-rose btb-layout-card"):
            gr.HTML(
                """
                <div class="btb-card-head">
                    <div>
                        <div class="btb-card-head__eyebrow">Auth</div>
                        <h3>账号登录</h3>
                        <p>推荐扫码登录；也支持导入已有 cookie 配置文件继续使用。</p>
                    </div>
                    <span class="btb-badge-pink">登录配置</span>
                </div>
                """
            )

            with gr.Row(elem_classes="btb-split-grid !items-stretch"):
                with gr.Column(elem_classes="btb-subcard", scale=4):
                    gr.HTML(
                        """
                        <div class="btb-inline-panel">
                            <div class="btb-inline-panel__eyebrow">Scan Login</div>
                            <h4>扫码授权</h4>
                            <p>先生成二维码，再用手机客户端完成扫码确认。</p>
                        </div>
                        """
                    )
                    qr_img = gr.Image(
                        label="登录二维码",
                        visible=False,
                        elem_classes="btb-qr-preview",
                    )
                    login_btn = gr.Button(
                        "注销并生成二维码登录",
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
                            <div class="btb-inline-panel__eyebrow">Current Session</div>
                            <h4>当前账号状态</h4>
                            <p>你可以查看当前登录账号，也可以导入已有登录文件。</p>
                        </div>
                        """
                    )
                    username_ui = gr.Textbox(
                        value=lambda: util.main_request.get_request_name(),
                        label="账号名称",
                        interactive=False,
                        info="导入配置文件后会自动读取账号名称",
                    )
                    gr_file_ui = gr.File(
                        label="当前登录信息文件",
                        value=lambda: GLOBAL_COOKIE_PATH,
                    )
                    upload_ui = gr.UploadButton(
                        label="导入现有登录文件",
                        elem_classes="btb-soft-button",
                    )

            def on_login_click():
                util.main_request.cookieManager.db.delete("cookie")
                gr.Info("已经注销，请重新扫码登录", duration=5)
                img_path, msg_or_key = start_login()
                if img_path:
                    return [
                        gr.update(value=img_path, visible=True),
                        gr.update(value="未登录"),
                        gr.update(value=GLOBAL_COOKIE_PATH),
                        msg_or_key,
                    ]
                gr.Warning("生成二维码失败", duration=5)
                return [
                    gr.update(value="", visible=False),
                    gr.update(value="未登录"),
                    gr.update(value=GLOBAL_COOKIE_PATH),
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
                        set_main_request(BiliRequest(cookies_config_path=GLOBAL_COOKIE_PATH))
                        util.main_request.cookieManager.db.insert("cookie", cookies)
                        name = util.main_request.get_request_name()
                        gr.Info("登录成功", duration=5)
                        return [
                            gr.update(value=name),
                            gr.update(value=GLOBAL_COOKIE_PATH),
                            gr.update(visible=False),
                            gr.update(visible=False),
                            gr.update(value=_render_setting_steps("ticket", logged_in=True, configured=False)),
                        ]
                    except Exception:
                        pass

                name = util.main_request.get_request_name()
                gr.Warning(msg, duration=5)
                return [
                    gr.update(value=name),
                    gr.update(value=GLOBAL_COOKIE_PATH),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                ]

            login_btn.click(
                on_login_click,
                outputs=[qr_img, username_ui, gr_file_ui, qrcode_key_state],
            )

            @gr.on(qrcode_key_state.change, inputs=qrcode_key_state, outputs=check_btn)
            def qrcode_key_state_change(key):
                return gr.update(visible=bool(key))

            check_btn.click(
                on_check_login,
                inputs=[qrcode_key_state],
                outputs=[username_ui, gr_file_ui, qr_img, check_btn, step_status_ui],
            )
            upload_ui.upload(upload_file, [upload_ui], [username_ui, gr_file_ui, step_status_ui])

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

        with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card"):
            gr.HTML(
                """
                <div class="btb-card-head">
                    <div>
                        <div class="btb-card-head__eyebrow">Ticket Config</div>
                        <h3>票务配置</h3>
                        <p>输入活动链接获取票档，然后依次完成联系人、地址和实名购票人配置。</p>
                    </div>
                    <span class="btb-badge-pink">生成配置</span>
                </div>
                """
            )

            with gr.Row(elem_classes="btb-action-band !items-end"):
                ticket_id_ui = gr.Textbox(
                    label="想抢票的活动链接",
                    interactive=True,
                    info="例如 https://show.bilibili.com/platform/detail.html?id=84096",
                    scale=5,
                )
                ticket_id_btn = gr.Button(
                    "获取票务信息",
                    elem_classes="btb-strong-button",
                    scale=1,
                )

            info_ui = gr.HTML(visible=False, elem_classes="btb-ticket-summary")

            with gr.Column(visible=False, elem_id="ticket-detail", elem_classes="btb-detail-shell") as inner:
                with gr.Row(elem_classes="btb-split-grid !items-end"):
                    ticket_info_ui = gr.Dropdown(
                        label="选择票档",
                        interactive=True,
                        type="index",
                        info="请仔细确认票档和起售时间",
                    )
                    data_ui = Calendar(
                        type="string",
                        label="选择日期",
                        info="若活动有多日期场次，请先切换日期",
                        interactive=True,
                    )

                with gr.Row(elem_classes="btb-split-grid !items-end"):
                    people_buyer_name = gr.Textbox(
                        value=lambda: ConfigDB.get("people_buyer_name") or "",
                        label="联系人姓名",
                        placeholder="请输入姓名",
                        interactive=True,
                        info="必填",
                    )
                    people_buyer_phone = gr.Textbox(
                        value=lambda: ConfigDB.get("people_buyer_phone") or "",
                        label="联系人电话",
                        placeholder="请输入电话",
                        interactive=True,
                        info="必填",
                    )
                    address_ui = gr.Dropdown(
                        label="收货地址",
                        interactive=True,
                        type="index",
                        info="如果为空，请先在会员购补充地址",
                    )

                people_ui = gr.CheckboxGroup(
                    label="实名购票人",
                    interactive=True,
                    type="index",
                    info="勾选几位，就会生成几张票的配置",
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
                    outputs=[config_output_ui, config_file_ui, step_status_ui],
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
                    data_ui,
                    step_status_ui,
                ],
            )

            def on_submit_data(_date):
                global ticket_str_list
                global ticket_value
                global is_hot_project
                global project_id
                global project_name

                try:
                    res = util.main_request.get(
                        url=f"https://show.bilibili.com/api/ticket/project/infoByDate?id={project_id}&date={_date}"
                    )
                    payload = res.json()
                    ticket_that_day = payload.get("data")

                    if not ticket_that_day or "screen_list" not in ticket_that_day:
                        gr.Warning("该日期暂无票务信息。")
                        return [
                            gr.update(value=_date, visible=True),
                            gr.update(choices=[]),
                            gr.update(value="", visible=False),
                        ]

                    ticket_str_list = []
                    ticket_value = []

                    for screen in ticket_that_day["screen_list"]:
                        screen_name = screen["name"]
                        screen_id = screen["id"]
                        express_fee = int(screen.get("express_fee", 0))
                        for ticket in screen["ticket_list"]:
                            sale_start = ticket["sale_start"]
                            ticket_price = int(ticket["price"]) + express_fee
                            ticket["price"] = ticket_price
                            ticket["screen"] = screen_name
                            ticket["screen_id"] = screen_id
                            ticket["is_hot_project"] = is_hot_project
                            ticket_can_buy = "可购买" if ticket.get("clickable") else "不可购买"
                            ticket_str = (
                                f"{screen_name} - {ticket['desc']} - {_format_price(ticket_price)} - "
                                f"{ticket_can_buy} - 【起售时间：{sale_start}】"
                            )
                            ticket_str_list.append(ticket_str)
                            ticket_value.append(
                                {"project_id": project_id, "ticket": ticket}
                            )

                    return [
                        gr.update(value=_date, visible=True),
                        gr.update(choices=ticket_str_list),
                        gr.update(
                            value=_render_ticket_info_html(
                                title="票务信息",
                                badge="日期已更新",
                                lines=[
                                    ("当前票务日期", _date),
                                    ("票档数量", str(len(ticket_str_list))),
                                    ("展会名称", project_name),
                                    ("项目 ID", str(project_id)),
                                ],
                                hint="票档列表已按当前日期刷新，请重新确认起售时间。",
                            ),
                            visible=True,
                        ),
                    ]
                except Exception as exc:
                    logger.exception(exc)
                    gr.Warning("切换日期失败，未能获取对应日期的票务信息。")
                    return [
                        gr.update(),
                        gr.update(),
                        gr.update(value="", visible=False),
                    ]

            data_ui.change(
                fn=on_submit_data,
                inputs=data_ui,
                outputs=[data_ui, ticket_info_ui, info_ui],
            )
