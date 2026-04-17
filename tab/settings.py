import json
import os
import re
import html
from datetime import datetime, timedelta
import time
from typing import Any, Dict, List
from urllib.parse import urlparse, parse_qs

import gradio as gr
from gradio_calendar import Calendar
from loguru import logger
import qrcode
import requests

from util.BiliRequest import BiliRequest
from util import TEMP_PATH, GLOBAL_COOKIE_PATH, set_main_request, ConfigDB
import util
from util.CookieManager import parse_cookie_list

buyer_value: List[Dict[str, Any]] = []
addr_value: List[Dict[str, Any]] = []
ticket_value: List[Dict[str, Any]] = []
project_name: str = ""
ticket_str_list: List[str] = []
sales_dates = []
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
        if sid is None:
            continue
        if sid in seen_screen_ids:
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
    105: "下架",
    106: "已取消",
}


def filename_filter(filename):
    filename = re.sub('[/:*?"<>|]', "", filename)
    return filename


def _render_ticket_info_html(
    title: str,
    lines: list[tuple[str, str]],
    badge: str | None = None,
    hint: str | None = None,
) -> str:
    badge_html = (
        f'<span class="btb-badge-blue">{html.escape(badge)}</span>'
        if badge
        else ""
    )
    items_html = "".join(
        (
            f'<div class="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3 shadow-sm">'
            f'<p class="text-xs font-medium tracking-wide text-slate-500 dark:text-slate-400">{html.escape(label)}</p>'
            f'<p class="mt-1 text-sm text-slate-800 dark:text-slate-200 break-all">{html.escape(value)}</p>'
            "</div>"
        )
        for label, value in lines
    )
    hint_html = (
        f'<p class="mt-3 text-xs leading-5 text-slate-400 dark:text-slate-500">{html.escape(hint)}</p>'
        if hint
        else ""
    )
    return f"""
    <div class="rounded-2xl border border-slate-200 dark:border-slate-700 bg-gradient-to-br from-slate-50 via-white to-sky-50 dark:from-slate-900 dark:via-slate-900 dark:to-sky-900/20 p-4 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
                <p class="text-sm font-semibold text-slate-900 dark:text-slate-100">{html.escape(title)}</p>
            </div>
            {badge_html}
        </div>
        <div class="mt-3 grid gap-3 md:grid-cols-2">
            {items_html}
        </div>
        {hint_html}
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
                    "无法从这个链接里识别票务 ID。请确认它是会员购活动详情页链接，格式类似：https://show.bilibili.com/platform/detail.html?id=84096",
                    duration=6,
                )
            extracted_id_message = f"已提取URL票ID：{num}"
        elif isinstance(num, str) and num.isdigit():
            num = int(num)
        else:
            raise gr.Error(
                "输入无效，请输入会员购活动详情页链接，或直接输入纯数字票务 ID。",
                duration=5,
            )
        res = util.main_request.get(
            url=f"https://show.bilibili.com/api/ticket/project/getV2?version=134&id={num}&project_id={num}"
        )
        ret = res.json()
        # logger.debug(ret)

        # 检查 errno
        if ret.get("errno", ret.get("code")) == 100001:
            raise gr.Error(
                "没有找到对应票务。请检查链接或票务 ID 是否正确。",
                duration=5,
            )
        elif ret.get("errno", ret.get("code")) != 0:
            raise gr.Error(
                ret.get("msg", ret.get("message", "未知错误")) + "。", duration=5
            )
        data = ret.get("data")
        if not isinstance(data, dict):
            raise gr.Error(
                "票务信息返回异常，可能这个链接不是标准会员购活动页，或者页面暂时不可用。",
                duration=6,
            )
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

        # Query infoByDate for each day in the activity date range to enrich screen/ticket enumeration.
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
            )
            good_list = good_list.json()
            ids = [item["id"] for item in good_list["data"]["list"]]
            for id in ids:
                good_detail = util.main_request.get(
                    url=f"https://show.bilibili.com/api/ticket/linkgoods/detail?link_id={id}"
                )
                good_detail = good_detail.json()
                for item in good_detail["data"]["specs_list"]:
                    item["project_id"] = good_detail["data"]["item_id"]
                    item["link_id"] = id
                data["screen_list"] += good_detail["data"]["specs_list"]
        except Exception as e:
            logger.warning(f"获取场贩商品信息出错: {e}")

        for screen in data["screen_list"]:
            if "name" not in screen:
                #  TODO 应该是跳转到会员购了
                continue
            screen_name = screen["name"]
            screen_id = screen["id"]
            project_id = screen["project_id"]
            express_fee = 0
            if data["has_eticket"]:
                express_fee = 0  # 电子票免费
            else:
                if screen["express_fee"] >= 0:
                    # -2 === t ? "快递到付" : -1 === t ? "快递包邮" : "快递配送"
                    express_fee = screen["express_fee"]

            for ticket in screen["ticket_list"]:
                ticket_desc = ticket["desc"]
                sale_start = ticket["sale_start"]
                ticket["price"] = ticket_price = ticket["price"] + express_fee
                ticket["screen"] = screen_name
                ticket["screen_id"] = screen_id
                ticket["is_hot_project"] = is_hot_project
                if "link_id" in screen:
                    ticket["link_id"] = screen["link_id"]
                ticket_can_buy = sales_flag_number_map[ticket["sale_flag_number"]]
                ticket_str = f"{screen_name} - {ticket_desc} - ￥{ticket_price / 100}- {ticket_can_buy} - 【起售时间：{sale_start}】"
                ticket_str_list.append(ticket_str)
                ticket_value.append(
                    {"project_id": screen["project_id"], "ticket": ticket}
                )

        buyer_json = util.main_request.get(
            url=f"https://show.bilibili.com/api/ticket/buyer/list?is_default&projectId={project_id}"
        ).json()
        logger.debug(buyer_json)
        addr_json = util.main_request.get(
            url="https://show.bilibili.com/api/ticket/addr/list"
        ).json()
        logger.debug(addr_json)
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
                        ("开展时间", f"{project_start_time} - {project_end_time}"),
                        ("场馆地址", f"{venue_name} {venue_address}"),
                    ],
                    hint=extracted_id_message
                    or "票务信息获取成功，请继续选择票档和购票人。",
                ),
                visible=True,
            ),
            gr.update(visible=True, value=sales_dates[0])
            if sales_dates_show
            else gr.update(visible=False),
        ]
    except gr.Error as e:
        gr.Warning(e.message)
        yield _empty_ticket_info_updates()
    except Exception as e:
        logger.exception(e)
        gr.Warning(
            "获取票务信息失败。请确认你输入的是会员购活动详情页链接，或稍后重试。"
        )
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
            raise gr.Error("你所填不是网址，或者网址是错的", duration=5)
        if len(people_indices) == 0:
            raise gr.Error("至少选一个实名人", duration=5)
        if addr_value is None:
            raise gr.Error("没有填写地址", duration=5)
        if ticket_info is None:
            raise gr.Error("没有填写选票", duration=5)
        if not people_buyer_name:
            raise gr.Error("没有填写联系人姓名", duration=5)
        if not people_buyer_phone:
            raise gr.Error("没有填写联系人电话", duration=5)
        if address_index is None:
            raise gr.Error("没有填写地址", duration=5)
        ticket_cur: dict[str, Any] = ticket_value[ticket_info]
        people_cur = [buyer_value[item] for item in people_indices]
        ticket_id = extract_id_from_url(ticket_id)
        if ticket_id is None:
            raise gr.Error(
                "当前填写的链接里没有识别到票务 ID，请重新获取票务信息后再生成配置。",
                duration=5,
            )

        ConfigDB.insert("people_buyer_name", people_buyer_name)
        ConfigDB.insert("people_buyer_phone", people_buyer_phone)

        address_cur = addr_value[address_index]
        username = util.main_request.get_request_name()
        detail = f"{username}-{project_name}-{ticket_str_list[ticket_info]}"
        for p in people_cur:
            detail += f"-{p['name']}"
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
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(config_dir, f, ensure_ascii=False, indent=4)
        yield [
            gr.update(value=config_dir, visible=True),
            gr.update(value=filename, visible=True),
        ]
    except gr.Error as e:
        gr.Warning(e.message)
    except Exception:
        raise gr.Error("生成错误，仔细看看你可能有哪里漏填的", duration=5)


def upload_file(filepath):
    try:
        set_main_request(BiliRequest(cookies_config_path=filepath))
        name = util.main_request.get_request_name()
        gr.Info("导入成功", duration=5)
        yield [
            gr.update(value=name),
            gr.update(value=ConfigDB.get("cookies_path")),
        ]
    except Exception as e:
        name = util.main_request.get_request_name()
        logger.exception(e)
        raise gr.Error("登录出现错误", duration=5)


def setting_tab():
    with gr.Column(elem_classes="!gap-5"):
        # 顶部提示卡片
        gr.Markdown(
            """
        <div class="btb-card btb-card-amber">
            <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <p class="text-lg font-semibold text-slate-900 dark:text-slate-100">使用前必读</p>
                    <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">
                        请确保在抢票前已完成基础资料填写，否则后续生成配置时可能没有可选项。
                    </p>
                </div>
                <span class="btb-badge-amber">
                    准备检查
                </span>
            </div>
            <div class="mt-4 grid gap-3 md:grid-cols-2">
                <div class="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3">
                    <p class="text-sm font-semibold text-slate-800 dark:text-slate-200">收货地址</p>
                    <p class="mt-1 text-sm text-slate-600 dark:text-slate-400">会员购中心 → 地址管理</p>
                </div>
                <div class="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-4 py-3">
                    <p class="text-sm font-semibold text-slate-800 dark:text-slate-200">购买人信息</p>
                    <p class="mt-1 text-sm text-slate-600 dark:text-slate-400">会员购中心 → 购买人信息</p>
                </div>
            </div>
            <p class="mt-4 text-xs leading-5 text-slate-500 dark:text-slate-500">
                即使暂时不需要，也建议提前填写完整，避免生成表单时没有任何候选项。
            </p>
        </div>
        """,
            elem_classes="!p-0",
        )

        # 登录信息卡片
        with gr.Column(elem_classes="btb-card btb-card-rose"):
            gr.Markdown(
                """
                <div class="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <p class="text-lg font-semibold text-slate-900 dark:text-slate-100">账号登录</p>
                        <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">
                            如果遇到登录问题，可使用
                            <a href="https://login.bilibili.bi/" class="font-medium text-sky-700 dark:text-sky-400 underline decoration-sky-300 dark:decoration-sky-500 underline-offset-4 hover:text-sky-900 dark:hover:text-sky-300" target="_blank">备用登录入口</a>。
                            导入配置文件属于临时登录；想长期使用同一账号，建议使用扫码登录。
                        </p>
                    </div>
                    <span class="btb-badge-pink">
                        登录配置
                    </span>
                </div>
                """,
                elem_classes="!p-0",
            )

            with gr.Row(elem_classes="!items-end !gap-3"):
                username_ui = gr.Text(
                    lambda: util.main_request.get_request_name(),
                    label="账号名称",
                    interactive=False,
                    info="输入配置文件使用的账号名称",
                    scale=5,
                )
                gr_file_ui = gr.File(
                    label="当前登录信息文件", value=lambda: GLOBAL_COOKIE_PATH, scale=1
                )

            def generate_qrcode():
                global session_cookies
                headers = {
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
                }
                max_retry = 10
                for _ in range(max_retry):
                    res = requests.request(
                        "GET",
                        "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                        headers=headers,
                    )
                    res_json = res.json()
                    if res_json["code"] == 0:
                        break
                    time.sleep(1)
                else:
                    return None, "二维码生成失败"

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

                qr.make_image(fill_color="black", back_color="white").get_image().save(
                    path
                )
                return path, qrcode_key

            def poll_login(qrcode_key):
                headers = {"User-Agent": "Mozilla/5.0"}
                for _ in range(120):  # 轮询60秒，每0.5秒一次
                    res = requests.request(
                        "GET",
                        "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                        params={"qrcode_key": qrcode_key},
                        headers=headers,
                        timeout=5,
                    )
                    poll_res = res.json()
                    if poll_res.get("code") == 0:
                        code = poll_res["data"]["code"]
                        if code == 0:
                            # 登录成功 requests.utils.dict_from_cookiejar(
                            cookies = parse_cookie_list(res.headers["set-cookie"])
                            return "登录成功！", cookies
                        elif code in (86101, 86090):
                            # 等待扫码或确认
                            time.sleep(0.5)
                            continue
                        else:
                            return f"扫码失败：{poll_res['data']['message']}", None
                    else:
                        time.sleep(0.5)
                return "登录超时，请重试。", None

            def start_login():
                img_path, qrcode_key = generate_qrcode()
                if not img_path:
                    return None, "二维码生成失败"
                return img_path, qrcode_key

            qr_img = gr.Image(label="登录验证码", visible=False)
            check_btn = gr.Button("扫码后点击此按钮", visible=False)

            with gr.Row(elem_classes="!items-center !gap-3 !flex-wrap"):
                login_btn = gr.Button(
                    "注销并生成二维码登录",
                    elem_classes="!rounded-xl !border !border-slate-300 dark:border-slate-600 !px-4 !shadow-sm transition",
                )

                qrcode_key_state = gr.State("")

                def on_login_click():
                    util.main_request.cookieManager.db.delete("cookie")
                    gr.Info("已经注销，请重新登录", duration=5)
                    img_path, msg_or_key = start_login()
                    if img_path:
                        gr.Info("已经生成二维码", duration=5)
                        return [
                            gr.update(value=img_path, visible=True),
                            gr.update(value="未登录"),
                            gr.update(value=GLOBAL_COOKIE_PATH),
                            msg_or_key,
                        ]

                    else:
                        gr.Warning("生成二维码异常", duration=5)
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
                        ]
                    msg, cookies = poll_login(key)
                    if cookies:
                        try:
                            # 扫码登录使用 GLOBAL_COOKIE_PATH
                            set_main_request(
                                BiliRequest(cookies_config_path=GLOBAL_COOKIE_PATH)
                            )
                            util.main_request.cookieManager.db.insert("cookie", cookies)
                            name = util.main_request.get_request_name()
                            if name:
                                gr.Info("登录成功", duration=5)
                            return [
                                gr.update(value=name),
                                gr.update(value=GLOBAL_COOKIE_PATH),
                                gr.update(visible=False),
                                gr.update(visible=False),
                            ]
                        except Exception:
                            pass

                    name = util.main_request.get_request_name()
                    gr.Warning(f"登录出现错误 {msg}", duration=5)
                    return [
                        gr.update(value=name),
                        gr.update(value=GLOBAL_COOKIE_PATH),
                        gr.update(),
                        gr.update(),
                    ]

                login_btn.click(
                    on_login_click,
                    outputs=[qr_img, username_ui, gr_file_ui, qrcode_key_state],
                )

                @gr.on(
                    qrcode_key_state.change, inputs=qrcode_key_state, outputs=check_btn
                )
                def qrcode_key_state_change(key):
                    if key:
                        return gr.update(visible=True)

                check_btn.click(
                    on_check_login,
                    inputs=[qrcode_key_state],
                    outputs=[username_ui, gr_file_ui, qr_img, check_btn],
                )
                upload_ui = gr.UploadButton(
                    label="导入",
                    elem_classes="!rounded-xl !border !border-slate-200 dark:border-slate-700 !shadow-sm",
                )
                upload_ui.upload(upload_file, [upload_ui], [username_ui, gr_file_ui])

        # 手机号输入卡片
        with gr.Accordion(
            label="填写你的当前账号所绑定的手机号[可选]",
            open=False,
            elem_classes="btb-card",
        ):
            phone_gate_ui = gr.Textbox(
                label="填写你的当前账号所绑定的手机号",
                info="手机号验证出现概率极低，可不填",
                value=util.main_request.cookieManager.get_config_value("phone", ""),
            )

            def input_phone(_phone):
                util.main_request.cookieManager.set_config_value("phone", _phone)

            phone_gate_ui.change(fn=input_phone, inputs=phone_gate_ui, outputs=None)

        # 抢票信息卡片
        with gr.Column(elem_classes="btb-card btb-card-sky"):
            gr.Markdown(
                """
                <div class="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <p class="text-lg font-semibold text-slate-900 dark:text-slate-100">票务配置</p>
                        <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">
                            输入活动链接后获取票档信息，再完成购票人、地址和联系人配置。
                        </p>
                    </div>
                    <span class="btb-badge-blue">
                        生成配置
                    </span>
                </div>
                """,
                elem_classes="!p-0",
            )
            info_ui = gr.HTML(
                label="配置票的信息",
                visible=False,
            )
            with gr.Row(elem_classes="!items-end !gap-3"):
                ticket_id_ui = gr.Textbox(
                    label="想要抢票的网址",
                    interactive=True,
                    info="形如 https://show.bilibili.com/platform/detail.html?id=84096",
                    scale=5,
                )
                ticket_id_btn = gr.Button(
                    "获取票信息",
                    elem_classes="!rounded-xl !border !border-sky-200 !bg-sky-100 !px-4 !text-sky-950 !shadow-sm hover:!bg-sky-200 !transition",
                    scale=1,
                )

            with gr.Column(
                visible=False,
                elem_id="ticket-detail",
                elem_classes="!gap-4 !rounded-2xl !border border-slate-200 dark:border-slate-700 bg-white/50 dark:bg-slate-800/50 !p-4",
            ) as inner:
                with gr.Row(elem_classes="!gap-3 !items-end"):
                    ticket_info_ui = gr.Dropdown(
                        label="选票",
                        interactive=True,
                        type="index",
                        info="必填，请仔细核对起售时间，千万别选错其他时间点的票",
                    )
                    data_ui = Calendar(
                        type="string",
                        label="选择日期",
                        info="此票需要你选择的时间,时间是否有效请自行判断",
                        interactive=True,
                    )

                with gr.Row(elem_classes="!gap-3 !items-end"):
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
                        label="地址",
                        interactive=True,
                        type="index",
                        info="必填，如果候选项为空请到「地址管理」添加",
                    )
                people_ui = gr.CheckboxGroup(
                    label="身份证实名认证",
                    interactive=True,
                    type="index",
                    info="必填，选几个就代表买几个人的票，在哔哩哔哩客户端-会员购-个人中心-购票人信息中添加",
                )

                config_btn = gr.Button(
                    "生成配置",
                    elem_classes="!rounded-xl !border !border-emerald-200 !bg-emerald-100 !px-4 !text-emerald-950 !shadow-sm hover:!bg-emerald-200 !transition",
                )
                config_file_ui = gr.File(visible=False)
                config_output_ui = gr.JSON(
                    label="生成配置文件（右上角复制）", visible=False
                )

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
                    data_ui,
                ],
            )

            def on_submit_data(_date):
                global ticket_str_list
                global ticket_value
                global is_hot_project
                try:
                    ticket_that_day = util.main_request.get(
                        url=f"https://show.bilibili.com/api/ticket/project/infoByDate?id={project_id}&date={_date}"
                    ).json()["data"]
                    ticket_str_list = []
                    ticket_value = []
                    for screen in ticket_that_day["screen_list"]:
                        screen_name = screen["name"]
                        screen_id = screen["id"]
                        express_fee = screen["express_fee"]
                        for ticket in screen["ticket_list"]:
                            ticket_desc = ticket["desc"]
                            sale_start = ticket["sale_start"]
                            ticket_price = ticket["price"] + express_fee
                            ticket["price"] = ticket_price
                            ticket["screen"] = screen_name
                            ticket["screen_id"] = screen_id
                            ticket["is_hot_project"] = is_hot_project
                            ticket_can_buy = (
                                "可购买" if ticket["clickable"] else "不可购买"
                            )
                            ticket_str = f"{screen_name} - {ticket_desc} - ￥{ticket_price / 100}- {ticket_can_buy} - 【起售时间：{sale_start}】"
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
                                    ("当前票日期", _date),
                                    ("票档数量", str(len(ticket_str_list))),
                                    ("展会名称", project_name),
                                    ("项目 ID", str(project_id)),
                                ],
                                hint="票档列表已按所选日期刷新，请重新核对起售时间。",
                            ),
                            visible=True,
                        ),
                    ]
                except Exception as e:
                    logger.exception(e)
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
