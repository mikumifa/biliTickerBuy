from __future__ import annotations

import datetime
import html
import os
import uuid

import gradio as gr
import requests

import util
from app_cmd.config.BwsConfig import BwsConfig
from interface.bws import (
    default_bws_year,
    effective_bws_reserve_begin_time,
    get_bws_reserve_context,
    resolve_bws_reserve_dates,
)
from tab.log import refresh_task_panel, render_task_manager_panel, visible_task_entries
from task.bws import bws_new_terminal
from util import GLOBAL_COOKIE_PATH, GlobalStatusInstance, LOG_DIR, set_main_request
from util.request.BiliRequest import BiliRequest
from util.request.CookieManager import CookieManager


CURRENT_COOKIE_UID = "__current_cookie__"


def _format_account_choice(uid: str, name: str, level: int) -> str:
    return f"{uid} - {name} (Lv{level})"


def _find_uid_from_choice(choice: str | None) -> str:
    if not choice:
        return ""
    return choice.split(" - ")[0] if " - " in choice else str(choice)


def _local_cookie_manager() -> CookieManager:
    return CookieManager(GLOBAL_COOKIE_PATH)


def _cookies_to_header(cookies: list[dict] | None) -> str:
    parts: list[str] = []
    for cookie in cookies or []:
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def _cookie_value(cookies: list[dict] | None, name: str) -> str | None:
    for cookie in cookies or []:
        if cookie.get("name") == name:
            value = cookie.get("value")
            return str(value) if value is not None else None
    return None


def _validate_cookies_with_nav(cookies: list[dict] | None) -> tuple[bool, str, str | None]:
    if not cookies:
        return False, "本地 Cookie 为空，请先在“账号登录”页登录。", None
    if not _cookie_value(cookies, "SESSDATA"):
        return False, "Cookie 缺少 SESSDATA，请重新登录。", None
    if not _cookie_value(cookies, "bili_jct"):
        return False, "Cookie 缺少 bili_jct，无法进行 BW 乐园预约。", None

    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "referer": "https://show.bilibili.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "cookie": _cookies_to_header(cookies),
    }
    try:
        response = requests.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return False, f"验证 Cookie 请求失败：{exc}", None

    if payload.get("code") != 0:
        return False, f"验证 Cookie 失败：[{payload.get('code')}] {payload.get('message', '')}", None
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict) or not data.get("isLogin"):
        return False, "Cookie 无效或已过期，请重新登录。", None
    username = str(data.get("uname") or "").strip()
    uid = str(data.get("mid") or _cookie_value(cookies, "DedeUserID") or "").strip()
    if not username:
        return False, "Cookie 验证通过但未返回用户名，请重新登录。", uid or None
    return True, f"当前账号：{username}", uid or None


def _get_account_choices() -> list[str]:
    manager = _local_cookie_manager()
    choices = [
        _format_account_choice(account.uid, account.name, account.level)
        for account in manager.get_accounts()
    ]
    try:
        current_cookies = manager.get_cookies(force=True)
    except Exception:
        current_cookies = None
    current_uid = _cookie_value(current_cookies, "DedeUserID")
    if current_cookies and current_uid:
        exists = any(_find_uid_from_choice(choice) == current_uid for choice in choices)
        if not exists:
            choices.insert(0, f"{current_uid} - 当前Cookie (本地当前)")
    elif current_cookies:
        choices.insert(0, f"{CURRENT_COOKIE_UID} - 当前Cookie (本地当前)")
    return choices


def _active_uid() -> str | None:
    try:
        manager = _local_cookie_manager()
        if not manager.have_cookies():
            return None
        uid = manager.get_cookies_value("DedeUserID")
        return str(uid) if uid else None
    except Exception:
        return None


def _default_account_choice(choices: list[str]) -> str | None:
    active_uid = _active_uid()
    if active_uid:
        for choice in choices:
            if _find_uid_from_choice(choice) == active_uid:
                return choice
    return choices[0] if choices else None


def _activate_local_account(choice: str | None) -> tuple[bool, str]:
    uid = _find_uid_from_choice(choice)
    if not uid:
        return False, "请选择一个本地账号。"
    manager = _local_cookie_manager()
    account = manager.find_by_uid(uid)
    if account is not None:
        cookies = account.cookies
    else:
        cookies = manager.get_cookies(force=True)
        current_uid = _cookie_value(cookies, "DedeUserID")
        if uid != CURRENT_COOKIE_UID and current_uid and uid != current_uid:
            return False, f"未找到本地账号 {uid}。"
    ok, message, _verified_uid = _validate_cookies_with_nav(cookies)
    if not ok:
        return False, message

    set_main_request(BiliRequest(cookies_config_path=GLOBAL_COOKIE_PATH))
    util.main_request.cookieManager.db.insert("cookie", cookies)
    return True, message


def _current_login_message() -> str:
    try:
        choices = _get_account_choices()
        if not choices:
            return "本地没有保存账号，请先在“账号登录”页完成登录。"
        manager = _local_cookie_manager()
        if not manager.have_cookies():
            return "本地已有账号，请在下方选择账号并验证 Cookie。"
        ok, message, _uid = _validate_cookies_with_nav(manager.get_cookies(force=True))
        return message if ok else f"{message} 请在下方选择账号重新验证，或在“账号登录”页重新登录。"
    except Exception:
        return "本地账号状态读取失败，请在“账号登录”页重新登录。"


def _require_login() -> None:
    message = _current_login_message()
    if "当前账号：" not in message:
        raise gr.Error(message)


def _format_ts(value) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return "-"
    try:
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return str(value)


def _reserved_activity_ids(my_reservations: dict | None) -> set[int]:
    reserved_ids: set[int] = set()
    reserve_list = my_reservations.get("reserve_list") if isinstance(my_reservations, dict) else None
    if not isinstance(reserve_list, dict):
        return reserved_ids
    for activities in reserve_list.values():
        if not isinstance(activities, list):
            continue
        for activity in activities:
            if not isinstance(activity, dict):
                continue
            try:
                reserved_ids.add(int(activity.get("reserve_id")))
            except (TypeError, ValueError):
                continue
    return reserved_ids


def _activity_status(activity: dict, reserved_ids: set[int]) -> str:
    try:
        reserve_id = int(activity.get("reserve_id"))
    except (TypeError, ValueError):
        reserve_id = -1
    if reserve_id in reserved_ids:
        return "已预约"
    state = activity.get("state")
    if state == 3:
        return "已结束"
    if state in (1, 2):
        return "可预约"
    if state is None:
        return "-"
    return f"状态{state}"


def _activity_kind(activity: dict) -> str:
    type_names = {
        1: "手渡会",
        2: "见面会",
        3: "签售会",
        4: "放映厅",
        5: "专访",
        6: "沉浸剧场",
        7: "占卜",
        8: "说书",
        9: "鉴宝",
        10: "演讲",
        11: "签名会",
        12: "见面会+签名会",
        13: "舞台观赏席位",
        14: "展台限定",
        15: "展台签售",
    }
    labels: list[str] = []
    for item in str(activity.get("act_type") or "").split(","):
        try:
            type_id = int(item)
        except ValueError:
            continue
        if type_id in type_names:
            labels.append(type_names[type_id])
    if activity.get("is_vip_ticket") is not None and activity.get("state") != 3:
        labels.append(
            "VIP预约时段"
            if int(activity.get("is_vip_ticket") or 0) == 1
            else "所有门票预约时段"
        )
    reserve_type = activity.get("reserve_type")
    if reserve_type == 1:
        labels.append("商品")
    elif reserve_type == 0:
        labels.append("活动")
    return " / ".join(labels) if labels else "活动"


def _format_activity_rows(reserve_info: dict, my_reservations: dict | None = None) -> str:
    reserve_list = reserve_info.get("reserve_list")
    user_ticket_info = reserve_info.get("user_ticket_info")
    if not isinstance(reserve_list, dict):
        return "<div class=\"btb-card-note\">未获取到预约项目列表。</div>"

    reserved_ids = _reserved_activity_ids(my_reservations)
    ticket_cards = ""
    if isinstance(user_ticket_info, dict) and user_ticket_info:
        cards: list[str] = []
        for date, ticket_info in user_ticket_info.items():
            if not isinstance(ticket_info, dict):
                continue
            ticket_line = " / ".join(
                item
                for item in [
                    str(ticket_info.get("screen_name") or ""),
                    str(ticket_info.get("sku_name") or ""),
                    str(ticket_info.get("ticket") or ""),
                ]
                if item
            )
            cards.append(
                '<div class="btb-mini-card">'
                f"<strong>{html.escape(str(date))}</strong>"
                f"<span>{html.escape(ticket_line or '已激活门票')}</span>"
                "</div>"
            )
        if cards:
            ticket_cards = (
                "<div class=\"btb-ticket-panel\"><h4>我的 BW 票种</h4>"
                f"<div class=\"btb-mini-grid\">{''.join(cards)}</div></div>"
            )

    rows: list[str] = []
    for date, activities in reserve_list.items():
        ticket = ""
        if isinstance(user_ticket_info, dict) and isinstance(
            user_ticket_info.get(date), dict
        ):
            ticket = str(user_ticket_info[date].get("ticket") or "")
        for activity in activities if isinstance(activities, list) else []:
            if not isinstance(activity, dict):
                continue
            title = str(activity.get("act_title") or "").replace("\n", "")
            reserve_id = activity.get("reserve_id", "")
            status = _activity_status(activity, reserved_ids)
            kind = _activity_kind(activity)
            ticket_info = (
                user_ticket_info.get(date)
                if isinstance(user_ticket_info, dict)
                and isinstance(user_ticket_info.get(date), dict)
                else None
            )
            reserve_begin_time = _format_ts(
                effective_bws_reserve_begin_time(activity, ticket_info)
            )
            act_time = "{0} - {1}".format(
                _format_ts(activity.get("act_begin_time")),
                _format_ts(activity.get("act_end_time")),
            )
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(date))}</td>"
                f"<td>{html.escape(str(reserve_id))}</td>"
                f"<td>{html.escape(status)}</td>"
                f"<td>{html.escape(kind)}</td>"
                f"<td>{html.escape(title)}</td>"
                f"<td>{html.escape(str(reserve_begin_time))}</td>"
                f"<td>{html.escape(act_time)}</td>"
                f"<td>{html.escape(ticket or '-')}</td>"
                "</tr>"
            )

    if not rows:
        return (
            ticket_cards
            + "<div class=\"btb-card-note\">暂无可显示的 BW 乐园预约项目。</div>"
        )

    return (
        ticket_cards
        +
        "<div class=\"btb-ticket-panel\">"
        "<h4>可预约项目</h4>"
        "<table class=\"btb-log-table\">"
        "<thead><tr><th>日期</th><th>预约ID</th><th>状态</th><th>类型</th><th>项目</th><th>预约开始</th><th>活动时间</th><th>门票号</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
    )


def _date_dropdown_update(reserve_dates_value: str, year_value: str):
    resolved_dates = resolve_bws_reserve_dates(
        str(reserve_dates_value or "").strip(),
        str(year_value or "").strip() or default_bws_year(),
    )
    choices = [date for date in resolved_dates.split(",") if date]
    return gr.update(
        choices=choices,
        value=choices[0] if choices else None,
    )


def _build_bws_task_log_path(reserve_id: int, reserve_date: str, year: str) -> str:
    suffix = reserve_date or year or "auto"
    filename = f"bws_{reserve_id}_{suffix}_{uuid.uuid4().hex[:8]}.log"
    safe_name = "".join(
        ch if ch.isalnum() or ch in "-_." else "_" for ch in filename
    )
    return os.path.join(LOG_DIR, safe_name)


def _bws_task_title(reserve_id: int, reserve_date: str, year: str) -> str:
    suffix = reserve_date or year or "自动日期"
    return f"BW预约 {reserve_id} / {suffix}"


def bws_tab():
    initial_account_choices = _get_account_choices()
    initial_year = default_bws_year()
    initial_reserve_dates = resolve_bws_reserve_dates("", initial_year).split(",")
    with gr.Column(elem_classes="btb-page-section"):
        with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card"):
            gr.HTML(
                """
                <div class="btb-card-head">
                    <div>
                        <h3>BW 乐园预约</h3>
                        <p>选择本地账号后可直接获取已激活票种和可预约项目。日期留空时会从 BW 官网自动获取最近一届日期。</p>
                    </div>
                </div>
                """
            )
            login_status = gr.HTML(
                value=lambda: f'<div class="btb-card-note">{html.escape(_current_login_message())}</div>'
            )
            with gr.Row(elem_classes="btb-action-band !items-end"):
                local_account = gr.Dropdown(
                    label="本地账号",
                    choices=initial_account_choices,
                    value=_default_account_choice(initial_account_choices),
                    interactive=True,
                    allow_custom_value=False,
                    filterable=False,
                    scale=4,
                )
                with gr.Column(scale=1, min_width=180):
                    refresh_btn = gr.Button(
                        "刷新账号状态",
                        elem_classes="btb-soft-button",
                    )
                    validate_account_btn = gr.Button(
                        "验证并使用账号",
                        elem_classes="btb-soft-button",
                    )
            with gr.Row(elem_classes="btb-action-band !items-end"):
                year = gr.Textbox(
                    label="年份参数",
                    value=initial_year,
                    placeholder="202601",
                    scale=1,
                )
                reserve_dates = gr.Textbox(
                    label="预约日期列表（可选）",
                    placeholder="留空自动从 BW 官网获取最近一届日期",
                    scale=3,
                )
                reserve_date = gr.Dropdown(
                    label="目标日期",
                    choices=initial_reserve_dates,
                    value=initial_reserve_dates[0] if initial_reserve_dates else None,
                    interactive=True,
                    allow_custom_value=False,
                    filterable=False,
                    scale=2,
                )
                reserve_type = gr.Radio(
                    label="预约类型",
                    choices=[("全部", -1), ("活动", 0), ("商品", 1)],
                    value=-1,
                    scale=2,
                )
            with gr.Row(elem_classes="!justify-end"):
                info_btn = gr.Button("获取预约信息", elem_classes="btb-soft-button")

            with gr.Row(elem_classes="btb-action-band !items-end"):
                reserve_id = gr.Textbox(
                    label="预约项目 ID",
                    value="",
                    placeholder="必填",
                    scale=2,
                )
                interval = gr.Number(
                    label="重试间隔（毫秒）",
                    value=300,
                    minimum=0,
                    precision=0,
                    scale=2,
                )
                retry_limit = gr.Number(
                    label="最大重试次数（0为持续重试）",
                    value=0,
                    minimum=0,
                    precision=0,
                    scale=2,
                )
            with gr.Row(elem_classes="!justify-end"):
                start_btn = gr.Button("开始预约", elem_classes="btb-strong-button")

            activity_panel = gr.HTML(
                value='<div class="btb-card-note">选择账号后点击“获取预约信息”，系统会拉取你的 BW 票种和可预约项目。</div>'
            )
            with gr.Column(
                visible=bool(visible_task_entries()),
                elem_classes="btb-card btb-card-sky btb-layout-card",
            ) as task_panel:
                task_refresh_token = render_task_manager_panel(task_panel)

    def refresh_login_status():
        choices = _get_account_choices()
        return (
            f'<div class="btb-card-note">{html.escape(_current_login_message())}</div>',
            gr.update(
                choices=choices,
                value=_default_account_choice(choices),
            ),
        )

    def validate_local_account(choice):
        ok, message = _activate_local_account(choice)
        if ok:
            gr.Info("账号 Cookie 验证通过。", duration=4)
        else:
            gr.Warning(message, duration=6)
        return f'<div class="btb-card-note">{html.escape(message)}</div>'

    def load_context(_reserve_dates, _reserve_type, _year):
        _require_login()
        year_value = str(_year or "").strip() or default_bws_year()
        reserve_dates_value = resolve_bws_reserve_dates(
            str(_reserve_dates or "").strip(),
            year_value,
        )
        context = get_bws_reserve_context(
            reserve_dates=reserve_dates_value,
            reserve_type=int(_reserve_type if _reserve_type is not None else -1),
            year=year_value,
            cookies_path=GLOBAL_COOKIE_PATH,
        )
        username = context.get("username", "未知账号")
        used_dates = context.get("reserve_dates", reserve_dates_value)
        return (
            f'<div class="btb-card-note">当前账号：{html.escape(str(username))}；已拉取日期：{html.escape(str(used_dates))}</div>',
            _format_activity_rows(
                context.get("reserve_info", {}),
                context.get("my_reservations", {}),
            ),
            _date_dropdown_update(str(used_dates), year_value),
        )

    def start_reserve(
        _reserve_id,
        _reserve_dates,
        _reserve_date,
        _reserve_type,
        _year,
        _interval,
        _retry_limit,
    ):
        _require_login()
        reserve_id_text = str(_reserve_id or "").strip()
        if not reserve_id_text:
            raise gr.Error("请填写预约项目 ID。")
        try:
            reserve_id_value = int(reserve_id_text)
        except ValueError:
            raise gr.Error("预约项目 ID 必须是正整数。") from None
        if reserve_id_value <= 0:
            raise gr.Error("预约项目 ID 必须大于 0。")
        year_value = str(_year or "").strip() or default_bws_year()
        dates_value = resolve_bws_reserve_dates(
            str(_reserve_dates or _reserve_date or "").strip(),
            year_value,
        )
        reserve_date_value = str(_reserve_date or "").strip()
        config = BwsConfig(
            reserve_id=reserve_id_value,
            reserve_dates=dates_value,
            reserve_date=reserve_date_value,
            reserve_type=int(_reserve_type if _reserve_type is not None else -1),
            year=year_value,
            interval=int(_interval or 0),
            retry_limit=int(_retry_limit or 0),
            cookies_path=GLOBAL_COOKIE_PATH,
            show_detail=True,
        )
        log_file_path = _build_bws_task_log_path(
            reserve_id_value,
            reserve_date_value,
            year_value,
        )
        proc = bws_new_terminal(config=config, log_file_path=log_file_path)
        GlobalStatusInstance.register_task_log(
            title=_bws_task_title(reserve_id_value, reserve_date_value, year_value),
            mode="终端",
            log_file=log_file_path,
            pid=proc.pid,
        )
        gr.Info("BW 乐园预约任务已启动，可在下方任务卡查看日志或终止进程。")
        return gr.update(visible=True)

    refresh_btn.click(refresh_login_status, outputs=[login_status, local_account])
    validate_account_btn.click(
        validate_local_account,
        inputs=local_account,
        outputs=login_status,
    )
    local_account.change(
        validate_local_account,
        inputs=local_account,
        outputs=login_status,
    )
    reserve_dates.change(
        _date_dropdown_update,
        inputs=[reserve_dates, year],
        outputs=reserve_date,
    )
    year.change(
        _date_dropdown_update,
        inputs=[reserve_dates, year],
        outputs=reserve_date,
    )
    info_btn.click(
        load_context,
        inputs=[reserve_dates, reserve_type, year],
        outputs=[login_status, activity_panel, reserve_date],
    )
    start_btn.click(
        start_reserve,
        inputs=[
            reserve_id,
            reserve_dates,
            reserve_date,
            reserve_type,
            year,
            interval,
            retry_limit,
        ],
        outputs=task_panel,
    ).then(
        fn=refresh_task_panel,
        inputs=None,
        outputs=[task_refresh_token, task_panel],
    )

    return refresh_login_status, [login_status, local_account]
