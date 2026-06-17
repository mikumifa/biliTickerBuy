import datetime
import html
import json
import os
import re
import threading
import time
import uuid

import gradio as gr
from gradio import SelectData
from loguru import logger

from tab.log import refresh_task_panel, render_task_manager_panel, visible_task_entries
from task.buy import buy_new_terminal
from util import (
    ConfigDB,
    GlobalStatusInstance,
    LOG_DIR,
    runtime_state_reader,
    runtime_state_writer,
    time_service,
)

BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8), name="Asia/Shanghai")
GO_UPLOADED_FILES_STATE_KEY = "go.uploaded_config_files"
DEFAULT_REQUEST_INTERVAL = 1000
DEFAULT_OUTER_INTERVAL = 0
DEFAULT_CREATE_RETRY_LIMIT = 20
DEFAULT_CREATE_REQUEST_BATCH_SIZE = 3
DEFAULT_PROXY_MAX_CONSECUTIVE_FAILURES = 2
DEFAULT_PROXY_COOLDOWN_SECONDS = 180
DEFAULT_PROXY_BACKOFF_MAX_SECONDS = 600
DEFAULT_LOG_RETENTION_DAYS = 7
DEFAULT_MAX_LOG_FILES = 200
DEFAULT_MAX_RUN_DIRS = 100


def _get_config_int(key: str, default: int) -> int:
    raw = ConfigDB.get(key)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value


def withTimeString(string):
    return (
        f"{datetime.datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}: {string}"
    )


def _build_task_log_path(filename: str) -> str:
    filename_only = os.path.splitext(os.path.basename(filename))[0]
    safe_name = "".join(
        ch if ch.isalnum() or ch in "-_." else "_" for ch in filename_only
    )
    safe_name = safe_name.strip("._") or "task"
    return os.path.join(LOG_DIR, f"{safe_name}_{uuid.uuid4().hex[:8]}.log")


def _parse_sale_start(value) -> datetime.datetime | None:
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value, tz=BEIJING_TZ)
    if isinstance(value, str) and value.strip():
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.datetime.strptime(value, fmt).replace(tzinfo=BEIJING_TZ)
            except ValueError:
                continue
    return None


def _preview_value(value) -> str:
    if value in (None, "", []):
        return "-"
    if isinstance(value, list):
        return "、".join(str(item) for item in value) if value else "-"
    return str(value)


def _format_price_cents(value) -> str:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        return _preview_value(value)
    return f"¥{amount / 100:.2f}"


def _format_buyer_identity(buyer_info) -> str:
    if not isinstance(buyer_info, list) or not buyer_info:
        return "-"

    id_type_map = {
        0: "身份证",
        1: "护照",
        2: "港澳居民来往内地通行证",
        3: "台湾居民来往大陆通行证",
        4: "外国人永久居留身份证",
    }
    items: list[str] = []
    for buyer in buyer_info:
        if not isinstance(buyer, dict):
            continue
        name = _preview_value(buyer.get("name"))
        id_type = id_type_map.get(buyer.get("id_type"), "未知证件")
        items.append(f"{name}（{id_type}）")
    return "、".join(items) if items else "-"


def _render_ticket_preview(config: dict) -> str:
    items = [
        ("账号", _preview_value(config.get("username"))),
        ("票数", _preview_value(config.get("count"))),
        ("单价", _format_price_cents(config.get("pay_money"))),
    ]
    item_html = "".join(
        (
            '<div class="btb-mini-card">'
            f"<strong>{html.escape(label)}</strong>"
            f"<span>{html.escape(value)}</span>"
            "</div>"
        )
        for label, value in items
    )
    return f"""
    <div class="btb-ticket-panel btb-ticket-panel--compact">
        <div class="btb-mini-grid btb-mini-grid--triple">{item_html}</div>
        <div class="btb-mini-card btb-ticket-panel__delivery">
            <strong>详细信息</strong>
            <span>{html.escape(_preview_value(config.get("detail") or "-"))}</span>
            <span>{html.escape(f"实名：{_format_buyer_identity(config.get('buyer_info'))}")}</span>
        </div>
    </div>
    """


@runtime_state_reader(GO_UPLOADED_FILES_STATE_KEY, kind="path_list")
def _get_session_upload_files() -> list[str]:
    return []


def _build_session_ticket_preview() -> str:
    files = _get_session_upload_files()
    if not files:
        return _render_ticket_preview({})
    try:
        with open(files[0], "r", encoding="utf-8") as file:
            content = json.load(file)
        return _render_ticket_preview(content)
    except Exception as e:
        return (
            f'<div class="btb-card-note">配置预览恢复失败：{html.escape(str(e))}</div>'
        )


def go_start_tab():
    auto_fill_time_default = ConfigDB.get("autoFillTime")
    if auto_fill_time_default is None:
        auto_fill_time_default = True

    with gr.Column(elem_classes="btb-page-section"):
        with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card"):
            with gr.Row(elem_classes="!items-stretch !gap-3"):
                upload_ui = gr.Files(
                    label="每一个上传的文件都会启动一个抢票程序",
                    file_count="multiple",
                    value=_get_session_upload_files,
                    scale=5,
                )
                with gr.Column(scale=4):
                    ticket_ui = gr.HTML(
                        value=_build_session_ticket_preview,
                        visible=True,
                    )
            with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card"):
                gr.HTML(
                    """
                    <div class="btb-card-head">
                        <div>
                            <h4>选择抢票时间</h3>
                            <p>
                                这里的时间按<strong>北京时间（UTC+8）</strong>填写。
                            </p>
                        </div>
                    </div>
                    """,
                    label="选择抢票的时间",
                )
                gr.HTML(
                    """
                    <div class="btb-time-picker-card">
                        <label class="btb-time-picker-card__label" for="datetime">
                            抢票开始时间
                        </label>
                        <input
                            type="datetime-local"
                            id="datetime"
                            name="datetime"
                            step="1"
                            class="btb-native-datetime-input"
                        >
                    </div>
                    """
                )
            with gr.Row(elem_classes="!justify-end"):
                auto_fill_time_btn = gr.Button(
                    "自动填写抢票时间",
                    elem_classes="btb-soft-button",
                    scale=0,
                    min_width=220,
                )

        with gr.Row(elem_classes="btb-inline-actions !justify-end"):
            interval_ui = gr.Number(
                label="抢票间隔",
                value=_get_config_int("requestInterval", DEFAULT_REQUEST_INTERVAL),
                minimum=1,
                info="抢票请求之间的时间间隔（单位：毫秒）",
            )

    @runtime_state_writer(GO_UPLOADED_FILES_STATE_KEY, kind="path_list")
    def upload(filepath):
        try:
            with open(filepath[0], "r", encoding="utf-8") as file:
                content = json.load(file)
            return gr.update(value=_render_ticket_preview(content), visible=True)
        except Exception as e:
            return gr.update(
                value=(
                    '<div class="btb-card-note">配置预览失败：'
                    f"{html.escape(str(e))}</div>"
                ),
                visible=True,
            )

    def file_select_handler(select_data: SelectData, files):
        file_label = files[select_data.index]
        try:
            with open(file_label, "r", encoding="utf-8") as file:
                content = json.load(file)
            return _render_ticket_preview(content)
        except Exception as e:
            return (
                f'<div class="btb-card-note">配置预览失败：{html.escape(str(e))}</div>'
            )

    def auto_fill_time(files):
        if not files:
            gr.Warning("请先上传至少一个抢票配置文件。")
            return ""

        sale_start_items: list[tuple[str, datetime.datetime]] = []
        adjusted_now = datetime.datetime.fromtimestamp(
            time.time() + time_service.get_timeoffset(),
            tz=BEIJING_TZ,
        )

        for filepath in files:
            with open(filepath, "r", encoding="utf-8") as file:
                config = json.load(file)

            sale_start = _parse_sale_start(
                config.get("sale_start", config.get("saleStart"))
            )
            if sale_start is None:
                raise gr.Error("缺少有效的 sale_start，请重新生成该配置。")
            sale_start_items.append((os.path.basename(filepath), sale_start))

        latest_sale_start = max(sale_start for _, sale_start in sale_start_items)
        unique_sale_starts = sorted({sale_start for _, sale_start in sale_start_items})
        if latest_sale_start <= adjusted_now:
            gr.Warning("已经过起售时间，不需要填写抢票时间。\n")
            return ""

        autofill_value = latest_sale_start.strftime("%Y-%m-%dT%H:%M:%S")
        if len(unique_sale_starts) == 1:
            gr.Info("已自动填写抢票时间。\n")
            return autofill_value

        gr.Warning(
            "抢票的起始时间不一样，已自动填写为最晚的起售时间，确保所有票档届时都已开始抢票。\n"
        )
        return autofill_value

    def split_proxies(https_proxy_list: list[str], task_num: int) -> list[list[str]]:
        assigned_proxies: list[list[str]] = [[] for _ in range(task_num)]
        for i, proxy in enumerate(https_proxy_list):
            assigned_proxies[i % task_num].append(proxy)
        return assigned_proxies

    def launch_task(
        filename: str,
        *,
        assigned_proxy: str,
        time_start: str,
        interval: int,
        audio_path: str,
        hide_random_message: bool,
        notify_proxy_exhausted: bool,
        show_qrcode: bool,
        use_local_token: bool,
        outer_interval: int,
        create_retry_limit: int,
        create_request_batch_size: int,
        proxy_max_consecutive_failures: int,
        proxy_cooldown_seconds: int,
        proxy_backoff_max_seconds: int,
        auto_open_payment_url: bool,
        log_level: str,
        log_retention_days: int,
    ):
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read()
        filename_only = os.path.basename(filename)
        logger.info(f"启动 {filename_only}")
        log_file_path = _build_task_log_path(filename_only)
        logger.info(f"任务 {filename_only} 的日志文件：{log_file_path}")
        proc = buy_new_terminal(
            tickets_info=content,
            time_start=time_start,
            interval=interval,
            audio_path=audio_path,
            pushplusToken=ConfigDB.get("pushplusToken"),
            serverchanKey=ConfigDB.get("serverchanKey"),
            serverchan3ApiUrl=ConfigDB.get("serverchan3ApiUrl"),
            barkToken=ConfigDB.get("barkToken"),
            ntfy_url=ConfigDB.get("ntfyUrl"),
            ntfy_username=ConfigDB.get("ntfyUsername"),
            ntfy_password=ConfigDB.get("ntfyPassword"),
            meowNickname=ConfigDB.get("meowNickname"),
            notify_proxy_exhausted=notify_proxy_exhausted,
            https_proxys=assigned_proxy,
            show_random_message=not hide_random_message,
            show_qrcode=show_qrcode,
            use_local_token=use_local_token,
            log_file_path=log_file_path,
            create_retry_limit=create_retry_limit,
            create_request_batch_size=create_request_batch_size,
            outer_loop_interval=outer_interval,
            proxy_max_consecutive_failures=proxy_max_consecutive_failures,
            proxy_cooldown_seconds=proxy_cooldown_seconds,
            proxy_backoff_max_seconds=proxy_backoff_max_seconds,
            auto_open_payment_url=auto_open_payment_url,
            log_level=log_level,
            log_retention_days=log_retention_days,
        )
        GlobalStatusInstance.register_task_log(
            title=filename_only,
            mode="终端",
            log_file=log_file_path,
            pid=proc.pid,
        )
        return proc

    def start_go(files, time_start, interval):
        if not files:
            gr.Warning("未提交抢票配置。")
            return gr.update(visible=False)

        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = DEFAULT_REQUEST_INTERVAL
        interval = max(1, interval)
        ConfigDB.insert("requestInterval", interval)

        https_proxys = ConfigDB.get("https_proxy") or ""
        https_proxy_list = ["none"] + https_proxys.split(",")
        assigned_proxies: list[list[str]] = []
        assigned_proxies_next_idx = 0

        audio_path = ConfigDB.get("audioPath") or ""
        hide_random_message = ConfigDB.get("hideRandomMessage")
        if hide_random_message is None:
            hide_random_message = True
        notify_proxy_exhausted = ConfigDB.get("notifyProxyExhausted")
        if notify_proxy_exhausted is None:
            notify_proxy_exhausted = False
        auto_open_payment_url = ConfigDB.get("autoOpenPaymentUrl")
        if auto_open_payment_url is None:
            auto_open_payment_url = True
        show_qrcode = ConfigDB.get("showQrcode")
        if show_qrcode is None:
            show_qrcode = True
        use_local_token = ConfigDB.get("useLocalToken")
        if use_local_token is None:
            use_local_token = False
        proxy_assignment_strategy = str(
            ConfigDB.get("proxyAssignmentStrategy") or "balanced"
        ).lower()
        log_level = str(ConfigDB.get("logLevel") or "standard").lower()
        outer_interval = _get_config_int("outerLoopInterval", DEFAULT_OUTER_INTERVAL)
        create_retry_limit = _get_config_int(
            "createRetryLimit",
            DEFAULT_CREATE_RETRY_LIMIT,
        )
        create_request_batch_size = _get_config_int(
            "createRequestBatchSize",
            DEFAULT_CREATE_REQUEST_BATCH_SIZE,
        )
        proxy_max_consecutive_failures = _get_config_int(
            "proxyMaxConsecutiveFailures",
            DEFAULT_PROXY_MAX_CONSECUTIVE_FAILURES,
        )
        proxy_cooldown_seconds = _get_config_int(
            "proxyCooldownSeconds",
            DEFAULT_PROXY_COOLDOWN_SECONDS,
        )
        proxy_backoff_max_seconds = _get_config_int(
            "proxyBackoffMaxSeconds",
            DEFAULT_PROXY_BACKOFF_MAX_SECONDS,
        )
        queue_concurrency_limit = _get_config_int("queueConcurrencyLimit", 0)
        log_retention_days = _get_config_int(
            "logRetentionDays",
            DEFAULT_LOG_RETENTION_DAYS,
        )
        auto_cleanup_logs = ConfigDB.get("autoCleanupLogs")
        if auto_cleanup_logs is None:
            auto_cleanup_logs = True
        if auto_cleanup_logs:
            from util.CleanupUtil import cleanup_runtime_artifacts

            cleanup_runtime_artifacts(
                logs_dir=LOG_DIR,
                runs_dir=os.path.join(os.path.dirname(LOG_DIR), "btb_runs"),
                retention_days=log_retention_days,
                max_log_files=_get_config_int("maxLogFiles", DEFAULT_MAX_LOG_FILES),
                max_run_dirs=_get_config_int("maxRunDirs", DEFAULT_MAX_RUN_DIRS),
            )

        launch_kwargs = {
            "time_start": time_start,
            "interval": interval,
            "audio_path": audio_path,
            "hide_random_message": hide_random_message,
            "notify_proxy_exhausted": notify_proxy_exhausted,
            "show_qrcode": show_qrcode,
            "use_local_token": use_local_token,
            "outer_interval": outer_interval,
            "create_retry_limit": create_retry_limit,
            "create_request_batch_size": create_request_batch_size,
            "proxy_max_consecutive_failures": proxy_max_consecutive_failures,
            "proxy_cooldown_seconds": proxy_cooldown_seconds,
            "proxy_backoff_max_seconds": proxy_backoff_max_seconds,
            "auto_open_payment_url": auto_open_payment_url,
            "log_level": log_level,
            "log_retention_days": log_retention_days,
        }

        if proxy_assignment_strategy == "queue":
            worker_count = len(https_proxy_list)
            if queue_concurrency_limit > 0:
                worker_count = min(worker_count, queue_concurrency_limit)
            worker_count = max(1, min(worker_count, len(files)))
            pending_files = list(files)
            pending_lock = threading.Lock()

            def queue_worker(proxy_slot: str):
                while True:
                    with pending_lock:
                        if not pending_files:
                            return
                        current_file = pending_files.pop(0)
                    try:
                        proc = launch_task(
                            current_file,
                            assigned_proxy=proxy_slot,
                            **launch_kwargs,
                        )
                        proc.wait()
                    except Exception as exc:
                        logger.exception(exc)

            for worker_idx in range(worker_count):
                threading.Thread(
                    target=queue_worker,
                    args=(https_proxy_list[worker_idx % len(https_proxy_list)],),
                    name=f"btb-queue-worker-{worker_idx + 1}",
                    daemon=True,
                ).start()
            gr.Info("抢票任务已按队列模式启动。")
            return gr.update(visible=True)

        for idx, filename in enumerate(files):
            if assigned_proxies == []:
                left_task_num = len(files) - idx
                assigned_proxies = split_proxies(https_proxy_list, left_task_num)
            launch_task(
                filename,
                assigned_proxy=",".join(assigned_proxies[assigned_proxies_next_idx]),
                **launch_kwargs,
            )
            assigned_proxies_next_idx += 1
        gr.Info("抢票任务已启动，下面可以直接查看日志链接或停止任务。")
        return gr.update(visible=True)

    @runtime_state_writer(GO_UPLOADED_FILES_STATE_KEY, kind="path_list")
    def sync_uploaded_files(files):
        return None

    @runtime_state_writer(
        GO_UPLOADED_FILES_STATE_KEY,
        kind="path_list",
        value_getter=lambda args, kwargs, result: [],
    )
    def clear_uploaded_files(_files):
        return gr.update(value=_render_ticket_preview({}), visible=True)

    upload_ui.upload(fn=upload, inputs=upload_ui, outputs=ticket_ui)
    upload_ui.change(fn=sync_uploaded_files, inputs=upload_ui, outputs=None)

    def maybe_auto_fill_time(files):
        if not ConfigDB.get("autoFillTime"):
            return ""
        return auto_fill_time(files)

    upload_ui.clear(
        fn=clear_uploaded_files,
        inputs=upload_ui,
        outputs=ticket_ui,
    )
    upload_ui.select(file_select_handler, upload_ui, ticket_ui)

    go_btn = gr.Button(
        "开始抢票",
        elem_classes="btb-strong-button",
    )
    with gr.Column(
        visible=bool(visible_task_entries()),
        elem_classes="btb-card btb-card-sky btb-layout-card",
    ) as task_panel:
        task_refresh_token = render_task_manager_panel(task_panel)

    _time_tmp = gr.Textbox(visible=False)
    _auto_fill_time_tmp = gr.Textbox(visible=False)
    auto_fill_time_btn.click(
        fn=auto_fill_time,
        inputs=upload_ui,
        outputs=_auto_fill_time_tmp,
    ).then(
        fn=None,
        inputs=_auto_fill_time_tmp,
        outputs=_time_tmp,
        js="""
        (value) => {
            const input = document.getElementById("datetime");
            if (input) {
                input.value = value || "";
            }
            return value || "";
        }
        """,
    )
    upload_ui.upload(
        fn=maybe_auto_fill_time,
        inputs=upload_ui,
        outputs=_auto_fill_time_tmp,
    ).then(
        fn=None,
        inputs=_auto_fill_time_tmp,
        outputs=_time_tmp,
        js="""
        (value) => {
            const input = document.getElementById("datetime");
            if (input) {
                input.value = value || "";
            }
            return value || "";
        }
        """,
    )
    go_btn.click(
        fn=None,
        inputs=None,
        outputs=_time_tmp,
        js='(x) => document.getElementById("datetime").value',
    )

    go_btn.click(
        fn=start_go,
        inputs=[upload_ui, _time_tmp, interval_ui],
        outputs=task_panel,
    ).then(
        fn=refresh_task_panel,
        inputs=None,
        outputs=[task_refresh_token, task_panel],
    )

    return task_refresh_token, task_panel


def go_settings_tab(header_ui):
    def _split_proxy_lines(proxy_text: str | None) -> list[str]:
        if not proxy_text:
            return []
        return [
            item.strip()
            for item in re.split(r"[\n,]+", proxy_text)
            if item and item.strip()
        ]

    def _serialize_proxy_text(proxy_text: str | None) -> str:
        return ",".join(_split_proxy_lines(proxy_text))

    def _format_proxy_text(proxy_text: str | None) -> str:
        return "\n".join(_split_proxy_lines(proxy_text))

    def get_latest_proxy():
        return _format_proxy_text(ConfigDB.get("https_proxy") or "")

    def input_https_proxy(_https_proxy):
        normalized_proxy = _serialize_proxy_text(_https_proxy)
        ConfigDB.insert("https_proxy", normalized_proxy)
        gr.Info("代理配置已保存。")
        return gr.update(value=_format_proxy_text(normalized_proxy))

    def clear_https_proxy():
        ConfigDB.insert("https_proxy", "")
        gr.Info("代理配置已清空。")
        return gr.update(value="")

    def test_proxy_connectivity(proxy_string, timeout):
        try:
            from util.ProxyTester import test_proxy_connectivity

            proxy_string = _serialize_proxy_text(proxy_string)
            if not proxy_string or proxy_string.strip() == "":
                proxy_string = "none"
            result = test_proxy_connectivity(proxy_string, int(timeout))
            return gr.update(value=result, visible=True)
        except Exception as e:
            return gr.update(value=f"❌ 测试过程中发生错误: {str(e)}", visible=True)

    def show_proxy_test_loading():
        return gr.update(value="正在测试代理连通性，请稍候...", visible=True)

    def inner_input_serverchan(x):
        ConfigDB.insert("serverchanKey", x)
        return gr.update(value=ConfigDB.get("serverchanKey"))

    def inner_input_serverchan3(x):
        ConfigDB.insert("serverchan3ApiUrl", x)
        return gr.update(value=ConfigDB.get("serverchan3ApiUrl"))

    def inner_input_pushplus(x):
        ConfigDB.insert("pushplusToken", x)
        return gr.update(value=ConfigDB.get("pushplusToken"))

    def inner_input_bark(x):
        ConfigDB.insert("barkToken", x)
        return gr.update(value=ConfigDB.get("barkToken"))

    def inner_input_meow(x):
        ConfigDB.insert("meowNickname", x)
        return gr.update(value=ConfigDB.get("meowNickname"))

    def inner_input_ntfy(x):
        ConfigDB.insert("ntfyUrl", x)
        return gr.update(value=ConfigDB.get("ntfyUrl"))

    def inner_input_ntfy_username(x):
        ConfigDB.insert("ntfyUsername", x)
        return gr.update(value=ConfigDB.get("ntfyUsername"))

    def inner_input_ntfy_password(x):
        ConfigDB.insert("ntfyPassword", x)
        return gr.update(value=ConfigDB.get("ntfyPassword"))

    def inner_input_audio_path(x):
        if not x:
            ConfigDB.insert("audioPath", "")
            return gr.update(value=None)

        ConfigDB.insert("audioPath", x)
        gr.Info("提示音已保存。")
        return gr.update(value=ConfigDB.get("audioPath"))

    def test_terminal_audio():
        audio_path = ConfigDB.get("audioPath")
        if not audio_path:
            return "错误: 请先上传提示音"

        try:
            from util.AudioUtil import AudioNotifier

            AudioNotifier(audio_path).send_message(
                "🎫 抢票测试",
                "这是一条终端版音频测试消息",
            )
            return "✅ 终端音频通知: 测试播放成功"
        except Exception as e:
            logger.exception(e)
            return f"❌ 终端音频通知: 测试播放失败 - {str(e)}"

    def test_all_push():
        try:
            from util.Notifier import NotifierManager

            return NotifierManager.test_all_notifiers(include_audio=False)
        except Exception as e:
            logger.exception(e)
            return f"错误: 测试过程中发生异常 - {str(e)}"

    def test_ntfy_connection():
        url = ConfigDB.get("ntfyUrl")
        username = ConfigDB.get("ntfyUsername")
        password = ConfigDB.get("ntfyPassword")

        if not url:
            return "错误: 请先设置Ntfy服务器URL"

        from util import NtfyUtil

        success, message = NtfyUtil.test_connection(url, username, password)
        return f"成功: {message}" if success else f"错误: {message}"

    def update_hide_random_message(value):
        ConfigDB.insert("hideRandomMessage", value)
        return gr.update(value=ConfigDB.get("hideRandomMessage"))

    def update_hide_header(value):
        ConfigDB.insert("hideHeader", value)
        return (
            gr.update(value=ConfigDB.get("hideHeader")),
            gr.update(visible=not value),
        )

    def update_auto_fill_time(value):
        ConfigDB.insert("autoFillTime", value)
        return gr.update(value=ConfigDB.get("autoFillTime"))

    def update_notify_proxy_exhausted(value):
        ConfigDB.insert("notifyProxyExhausted", value)
        return gr.update(value=ConfigDB.get("notifyProxyExhausted"))

    def update_show_qrcode(value):
        ConfigDB.insert("showQrcode", value)
        return gr.update(value=ConfigDB.get("showQrcode"))

    def update_auto_open_payment_url(value):
        ConfigDB.insert("autoOpenPaymentUrl", value)
        return gr.update(value=ConfigDB.get("autoOpenPaymentUrl"))

    def update_use_local_token(value):
        ConfigDB.insert("useLocalToken", value)
        return gr.update(value=ConfigDB.get("useLocalToken"))

    def update_proxy_assignment_strategy(value):
        ConfigDB.insert("proxyAssignmentStrategy", value)
        return gr.update(value=ConfigDB.get("proxyAssignmentStrategy"))

    def update_log_level(value):
        ConfigDB.insert("logLevel", value)
        return gr.update(value=ConfigDB.get("logLevel"))

    def update_auto_cleanup_logs(value):
        ConfigDB.insert("autoCleanupLogs", value)
        return gr.update(value=ConfigDB.get("autoCleanupLogs"))

    def update_request_interval(value):
        try:
            parsed = max(1, int(value))
        except (TypeError, ValueError):
            parsed = DEFAULT_REQUEST_INTERVAL
        ConfigDB.insert("requestInterval", parsed)
        return gr.update(
            value=_get_config_int("requestInterval", DEFAULT_REQUEST_INTERVAL)
        )

    def update_outer_loop_interval(value):
        try:
            parsed = max(0, int(value))
        except (TypeError, ValueError):
            parsed = DEFAULT_OUTER_INTERVAL
        ConfigDB.insert("outerLoopInterval", parsed)
        return gr.update(
            value=_get_config_int("outerLoopInterval", DEFAULT_OUTER_INTERVAL)
        )

    def update_create_retry_limit(value):
        try:
            parsed = max(1, int(value))
        except (TypeError, ValueError):
            parsed = DEFAULT_CREATE_RETRY_LIMIT
        ConfigDB.insert("createRetryLimit", parsed)
        return gr.update(
            value=_get_config_int("createRetryLimit", DEFAULT_CREATE_RETRY_LIMIT)
        )

    def update_create_request_batch_size(value):
        try:
            parsed = max(1, int(value))
        except (TypeError, ValueError):
            parsed = DEFAULT_CREATE_REQUEST_BATCH_SIZE
        ConfigDB.insert("createRequestBatchSize", parsed)
        return gr.update(
            value=_get_config_int(
                "createRequestBatchSize",
                DEFAULT_CREATE_REQUEST_BATCH_SIZE,
            )
        )

    def _update_positive_int_config(key: str, value, default: int):
        try:
            parsed = max(1, int(value))
        except (TypeError, ValueError):
            parsed = default
        ConfigDB.insert(key, parsed)
        return gr.update(value=_get_config_int(key, default))

    def update_proxy_max_consecutive_failures(value):
        return _update_positive_int_config(
            "proxyMaxConsecutiveFailures",
            value,
            DEFAULT_PROXY_MAX_CONSECUTIVE_FAILURES,
        )

    def update_proxy_cooldown_seconds(value):
        return _update_positive_int_config(
            "proxyCooldownSeconds",
            value,
            DEFAULT_PROXY_COOLDOWN_SECONDS,
        )

    def update_proxy_backoff_max_seconds(value):
        return _update_positive_int_config(
            "proxyBackoffMaxSeconds",
            value,
            DEFAULT_PROXY_BACKOFF_MAX_SECONDS,
        )

    def update_queue_concurrency_limit(value):
        try:
            parsed = max(0, int(value))
        except (TypeError, ValueError):
            parsed = 0
        ConfigDB.insert("queueConcurrencyLimit", parsed)
        return gr.update(value=_get_config_int("queueConcurrencyLimit", 0))

    def update_log_retention_days(value):
        return _update_positive_int_config(
            "logRetentionDays",
            value,
            DEFAULT_LOG_RETENTION_DAYS,
        )

    def update_max_log_files(value):
        return _update_positive_int_config(
            "maxLogFiles",
            value,
            DEFAULT_MAX_LOG_FILES,
        )

    def update_max_run_dirs(value):
        return _update_positive_int_config(
            "maxRunDirs",
            value,
            DEFAULT_MAX_RUN_DIRS,
        )

    hide_random_message_default = ConfigDB.get("hideRandomMessage")
    if hide_random_message_default is None:
        hide_random_message_default = True
    hide_header_default = ConfigDB.get("hideHeader")
    if hide_header_default is None:
        hide_header_default = False
    auto_fill_time_default = ConfigDB.get("autoFillTime")
    if auto_fill_time_default is None:
        auto_fill_time_default = True
    notify_proxy_exhausted_default = ConfigDB.get("notifyProxyExhausted")
    if notify_proxy_exhausted_default is None:
        notify_proxy_exhausted_default = False
    show_qrcode_default = ConfigDB.get("showQrcode")
    if show_qrcode_default is None:
        show_qrcode_default = True
    auto_open_payment_url_default = ConfigDB.get("autoOpenPaymentUrl")
    if auto_open_payment_url_default is None:
        auto_open_payment_url_default = True
    use_local_token_default = ConfigDB.get("useLocalToken")
    if use_local_token_default is None:
        use_local_token_default = False
    auto_cleanup_logs_default = ConfigDB.get("autoCleanupLogs")
    if auto_cleanup_logs_default is None:
        auto_cleanup_logs_default = True
    proxy_assignment_strategy_default = str(
        ConfigDB.get("proxyAssignmentStrategy") or "balanced"
    ).lower()
    log_level_default = str(ConfigDB.get("logLevel") or "standard").lower()
    request_interval_default = _get_config_int(
        "requestInterval",
        DEFAULT_REQUEST_INTERVAL,
    )
    outer_loop_interval_default = _get_config_int(
        "outerLoopInterval",
        DEFAULT_OUTER_INTERVAL,
    )
    create_retry_limit_default = _get_config_int(
        "createRetryLimit",
        DEFAULT_CREATE_RETRY_LIMIT,
    )
    create_request_batch_size_default = _get_config_int(
        "createRequestBatchSize",
        DEFAULT_CREATE_REQUEST_BATCH_SIZE,
    )
    proxy_max_consecutive_failures_default = _get_config_int(
        "proxyMaxConsecutiveFailures",
        DEFAULT_PROXY_MAX_CONSECUTIVE_FAILURES,
    )
    proxy_cooldown_seconds_default = _get_config_int(
        "proxyCooldownSeconds",
        DEFAULT_PROXY_COOLDOWN_SECONDS,
    )
    proxy_backoff_max_seconds_default = _get_config_int(
        "proxyBackoffMaxSeconds",
        DEFAULT_PROXY_BACKOFF_MAX_SECONDS,
    )
    queue_concurrency_limit_default = _get_config_int("queueConcurrencyLimit", 0)
    log_retention_days_default = _get_config_int(
        "logRetentionDays",
        DEFAULT_LOG_RETENTION_DAYS,
    )
    max_log_files_default = _get_config_int("maxLogFiles", DEFAULT_MAX_LOG_FILES)
    max_run_dirs_default = _get_config_int("maxRunDirs", DEFAULT_MAX_RUN_DIRS)

    with gr.Column(elem_classes="btb-page-section"):
        with gr.Tabs(elem_classes="btb-top-tabs"):
            with gr.Tab("代理"):
                with gr.Column(elem_classes="btb-card btb-layout-card"):
                    gr.Markdown("### 填写你的代理服务器")
                    https_proxy_ui = gr.Textbox(
                        label="代理服务器地址",
                        lines=4,
                        placeholder="每行填写一个代理地址，留空表示只使用直连\n例如：\nhttp://127.0.0.1:8080\nsocks5://127.0.0.1:1080\nhttp://proxyuser:proxypass@xx.xx.xx.xx:8080",
                        value=get_latest_proxy(),
                    )
                    with gr.Row(elem_classes="btb-inline-actions !justify-end"):
                        save_proxy_btn = gr.Button(
                            "保存代理配置",
                            elem_classes="btb-soft-button",
                        )
                        clear_proxy_btn = gr.Button(
                            "清空代理配置",
                            elem_classes="btb-soft-button",
                        )
                        test_proxy_btn = gr.Button(
                            "🔍 测试代理连通性",
                            elem_classes="btb-soft-button",
                        )
                    test_timeout_ui = gr.Number(
                        label="测试代理超时时间(秒)",
                        value=10,
                        minimum=5,
                        maximum=60,
                        step=1,
                    )
                    test_result_ui = gr.Textbox(
                        label="测试结果",
                        lines=10,
                        max_lines=15,
                        interactive=False,
                        placeholder="点击上方按钮开始测试代理连通性...",
                        visible=False,
                    )
                    gr.Markdown(
                        """
                        <div class="mt-3 text-sm leading-7 text-slate-700">
                          <p><strong>怎么填写：</strong>推荐每行填写一个代理地址，也支持逗号分隔。留空表示只使用直连。</p>
                          <p><strong>支持格式：</strong><code>http://IP:端口</code>、<code>https://IP:端口</code>、<code>socks5://IP:端口</code>。</p>
                          <p><strong>带账号密码的 HTTP 代理示例：</strong><code>http://proxyuser:proxypass@xx.xx.xx.xx:8080</code></p>
                          <p><strong>程序什么时候会用代理：</strong>当抢票流程检测到风控时，会按你填写的顺序切换到下一个代理；当前请求不会在请求层立刻自动重试，下一次抢票重试才会使用新代理。</p>
                          <p><strong>代理失效怎么处理：</strong>同一代理在短时间内连续失败会被暂时冷却；如果所有代理都不可用，程序会按递增时间休息后再试。</p>
                          <p><strong>建议先测试再开抢：</strong>保存后点击上方“测试代理连通性”，确认代理能正常访问哔哩哔哩接口。</p>
                          <p><strong>自建代理：</strong>如果你没有现成代理，可以自己在 Ubuntu / Debian 服务器上搭建 Squid HTTP 代理。</p>
                          <p><strong>完整搭建说明：</strong><a href="https://github.com/mikumifa/biliTickerBuy/blob/main/docs/proxy-self-hosting.md" target="_blank" rel="noopener noreferrer">GitHub 查看自建代理指南</a></p>
                        </div>
                        """
                    )
                    gr.Markdown("## 代理策略")
                    proxy_max_consecutive_failures_ui = gr.Number(
                        label="单代理最大连续失败次数",
                        value=proxy_max_consecutive_failures_default,
                        minimum=1,
                        step=1,
                        info="同一代理在短时间内连续失败多少次后进入冷却。",
                    )
                    proxy_cooldown_seconds_ui = gr.Number(
                        label="代理冷却时间（秒）",
                        value=proxy_cooldown_seconds_default,
                        minimum=1,
                        step=1,
                        info="代理进入冷却后，多久恢复可用。",
                    )
                    proxy_backoff_max_seconds_ui = gr.Number(
                        label="风控后休眠上限（秒）",
                        value=proxy_backoff_max_seconds_default,
                        minimum=1,
                        step=1,
                        info="当所有代理都暂时不可用时，程序退避休眠的最大时长。",
                    )
                    notify_proxy_exhausted_ui = gr.Checkbox(
                        label="无可用代理时发送提醒",
                        value=notify_proxy_exhausted_default,
                        info="默认关闭。开启后，当所有代理都进入冷却且程序需要休息时，会通过已配置的推送渠道提醒你补充代理。",
                    )

            with gr.Tab("音乐"):
                with gr.Column(elem_classes="btb-card btb-layout-card"):
                    gr.Markdown("### 配置抢票成功后播放音乐")
                    gr.Markdown(
                        "推荐上传 WAV。若上传 MP3、FLAC、M4A、OGG 等格式，请先在系统中安装 "
                        "`ffmpeg/ffprobe`；如果安装时报错，也可以先前往 "
                        "https://cloudconvert.com/wav-converter 转成 WAV 后再上传。"
                    )
                    audio_path_ui = gr.Audio(
                        label="上传提示声音",
                        type="filepath",
                        loop=True,
                        value=(ConfigDB.get("audioPath") or None),
                    )
                    test_audio_button = gr.Button(
                        "测试终端播放",
                        elem_classes="btb-soft-button",
                    )
                    test_audio_result = gr.Textbox(
                        label="音乐测试结果",
                        interactive=False,
                    )

            with gr.Tab("推送"):
                with gr.Column(elem_classes="btb-card btb-layout-card"):
                    gr.Markdown("### 配置抢票推送消息")
                    gr.Markdown(
                        """
                        🗨️ **抢票成功提醒**

                        > 你需要去对应的网站获取 key 或 token，然后填入下面的输入框  
                        > [Server酱<sup>Turbo</sup>](https://sct.ftqq.com/sendkey) | [pushplus](https://www.pushplus.plus/uc.html) | [Server酱<sup>3</sup>](https://sc3.ft07.com/sendkey) | [ntfy](https://ntfy.sh/) | [Bark](https://bark.day.app/) | MeoW  
                        > 留空以不启用提醒功能

                        ### 🔍 推送服务对比

                        | 服务     | 优点                               | 缺点                            |
                        |----------|------------------------------------|---------------------------------|
                        | Server酱<sup>Turbo</sup> | 简单易用，微信推送              | 微信推送很难看到 |
                        | pushplus | 简单易用，微信推送| 微信推送很难看到               |
                        | Server酱<sup>3</sup> | APP推送，有中文文档              | 配置复杂 |
                        | ntfy     | APP推送, 功能强大, 支持长期响铃 | 配置复杂，需要手动搭建或注册公网地址 |
                        | Bark     | iOS通知推送，配置简单，无视静音和勿扰模式，支持APP跳转 | 仅支持iOS设备 |
                        | MeoW     | HMS系统级通知推送，配置简单，无需后台常驻 | 仅支持鸿蒙设备 |

                        ✅ 推荐：初次使用建议选择 **pushplus** 或 **Server酱ᵀᵘʳᵇᵒ**，配置最简单  
                        🍎 iOS用户推荐使用 **Bark**，通知效果最佳  
                        ⭕ 鸿蒙用户推荐使用 **MeoW**，HMS系统级推送  
                        🛠️ 追求高度自由/有自建服务器/需要在抢票成功时通过手机播放铃声时，建议用 **ntfy** 或 **Server酱³**
                        """
                    )
                    gr.Markdown("#### Server酱")
                    serverchan_ui = gr.Textbox(
                        value=(ConfigDB.get("serverchanKey") or ""),
                        label="Server酱ᵀᵘʳᵇᵒ的SendKey｜输入完成后，回车键保存",
                        interactive=True,
                        info="https://sct.ftqq.com/",
                    )
                    serverchan3_ui = gr.Textbox(
                        value=(ConfigDB.get("serverchan3ApiUrl") or ""),
                        label="Server酱³的API URL｜输入完成后，回车键保存",
                        interactive=True,
                        info="https://sc3.ft07.com/",
                    )
                    gr.Markdown("#### PushPlus")
                    pushplus_ui = gr.Textbox(
                        value=(ConfigDB.get("pushplusToken") or ""),
                        label="PushPlus的Token｜输入完成后，回车键保存",
                        interactive=True,
                        info="https://www.pushplus.plus/",
                    )
                    gr.Markdown("#### Bark")
                    bark_ui = gr.Textbox(
                        value=(ConfigDB.get("barkToken") or ""),
                        label="Bark的Token｜输入完成后，回车键保存",
                        interactive=True,
                        info='iOS Bark App的"服务器"页面获取，例如: jmGYK*****(并非Device Token)；自托管服务请输入完整推送地址，例如: https://bark.example.app/jmGYK*****',
                    )
                    gr.Markdown("#### Meow")
                    meow_ui = gr.Textbox(
                        value=(ConfigDB.get("meowNickname") or ""),
                        label="MeoW昵称｜输入完成后，回车键保存",
                        interactive=True,
                        info="https://www.chuckfang.com/MeoW/api_doc.html",
                    )
                    gr.Markdown("#### Ntfy")
                    ntfy_ui = gr.Textbox(
                        value=(ConfigDB.get("ntfyUrl") or ""),
                        label="Ntfy服务器URL｜输入完成后，回车键保存",
                        interactive=True,
                        info="例如: https://ntfy.sh/your-topic",
                    )
                    with gr.Row(elem_classes="btb-inline-actions !justify-end"):
                        ntfy_username_ui = gr.Textbox(
                            value=(ConfigDB.get("ntfyUsername") or ""),
                            label="Ntfy用户名",
                            interactive=True,
                            info="如果你的Ntfy服务器需要认证",
                        )
                        ntfy_password_ui = gr.Textbox(
                            value=(ConfigDB.get("ntfyPassword") or ""),
                            label="Ntfy密码",
                            interactive=True,
                            type="password",
                        )
                    test_ntfy_button = gr.Button(
                        "测试Ntfy连接",
                        elem_classes="btb-soft-button",
                    )
                    test_ntfy_result = gr.Textbox(
                        label="测试结果",
                        interactive=False,
                    )
                    gr.Markdown("#### 测试")
                    test_all_push_button = gr.Button(
                        "🧪 测试所有推送",
                        elem_classes="!rounded-xl !border !border-slate-300 !bg-white !text-slate-900 !shadow-sm hover:!bg-slate-100 !transition",
                    )
                    test_push_result = gr.Textbox(
                        label="推送测试结果",
                        interactive=False,
                    )

            with gr.Tab("杂项"):
                with gr.Column(elem_classes="btb-card btb-layout-card"):
                    gr.Markdown("### 杂项配置")
                    gr.Markdown("## 支付")
                    show_qrcode_ui = gr.Checkbox(
                        label="抢票成功后显示付款二维码",
                        value=show_qrcode_default,
                        info="默认开启。关闭后，抢票成功时不再弹出付款二维码。",
                    )
                    auto_open_payment_url_ui = gr.Checkbox(
                        label="抢票成功后自动打开支付链接",
                        value=auto_open_payment_url_default,
                        info="默认关闭。开启后，成功获取支付链接时会尝试用系统默认浏览器打开。",
                    )
                    gr.Markdown("## 并发")
                    proxy_assignment_strategy_ui = gr.Dropdown(
                        label="任务代理分配策略",
                        choices=[
                            ("均匀分配", "balanced"),
                            ("队列模式", "queue"),
                        ],
                        value=proxy_assignment_strategy_default,
                        interactive=True,
                        allow_custom_value=False,
                        filterable=False,
                    )
                    queue_concurrency_limit_ui = gr.Number(
                        label="队列并发上限（仅队列模式）",
                        value=queue_concurrency_limit_default,
                        minimum=0,
                        step=1,
                        info="填 0 表示等于代理数量。",
                    )
                    gr.Markdown("## 日志")
                    log_level_ui = gr.Dropdown(
                        label="日志级别",
                        choices=[
                            ("简洁", "simple"),
                            ("标准", "standard"),
                            ("调试", "debug"),
                        ],
                        value=log_level_default,
                        interactive=True,
                        allow_custom_value=False,
                        filterable=False,
                    )
                    auto_cleanup_logs_ui = gr.Checkbox(
                        label="启动时自动清理日志",
                        value=auto_cleanup_logs_default,
                        info="默认开启。会清理 btb_logs 和 btb_runs 中过旧或过多的内容。",
                    )
                    log_retention_days_ui = gr.Number(
                        label="日志保留天数",
                        value=log_retention_days_default,
                        minimum=1,
                        step=1,
                    )
                    max_log_files_ui = gr.Number(
                        label="最多保留日志文件数",
                        value=max_log_files_default,
                        minimum=1,
                        step=1,
                    )
                    max_run_dirs_ui = gr.Number(
                        label="最多保留运行目录数",
                        value=max_run_dirs_default,
                        minimum=1,
                        step=1,
                    )
                    gr.Markdown("## 其他")
                    auto_fill_time_ui = gr.Checkbox(
                        label="默认自动填写抢票时间",
                        value=auto_fill_time_default,
                        info="开启后，上传抢票配置文件时会自动按票档起售时间回填抢票时间。",
                    )
                    show_random_message_ui = gr.Checkbox(
                        label="关闭群友语录",
                        value=hide_random_message_default,
                        info="关闭后，抢票失败时将不再显示有趣的语录",
                    )
                    hide_header_ui = gr.Checkbox(
                        label="隐藏顶部大 Header",
                        value=hide_header_default,
                        info="默认显示。开启后将隐藏顶部包含项目地址和图标的区域。",
                    )
                    use_local_token_ui = gr.Checkbox(
                        label="使用本地 token",
                        value=use_local_token_default,
                        info="默认关闭。开启后，非 hotproject 直接使用本地生成 token。",
                    )
                    request_interval_ui = gr.Number(
                        label="内层请求间隔（毫秒）",
                        value=request_interval_default,
                        minimum=1,
                        step=1,
                        info="创建订单内层循环的请求间隔。",
                    )
                    outer_loop_interval_ui = gr.Number(
                        label="外层批次间隔（毫秒）",
                        value=outer_loop_interval_default,
                        minimum=0,
                        step=1,
                        info="每批 create 请求失败后，下一批前等待多久。",
                    )
                    create_retry_limit_ui = gr.Number(
                        label="最大重试次数",
                        value=create_retry_limit_default,
                        minimum=1,
                        step=1,
                        info="create 阶段最多尝试多少次。",
                    )
                    create_request_batch_size_ui = gr.Number(
                        label="单批请求数",
                        value=create_request_batch_size_default,
                        minimum=1,
                        step=1,
                        info="每一批会连续发送多少次 create 请求。",
                    )

    save_proxy_btn.click(
        fn=input_https_proxy, inputs=https_proxy_ui, outputs=https_proxy_ui
    )
    clear_proxy_btn.click(fn=clear_https_proxy, outputs=https_proxy_ui)
    test_proxy_btn.click(
        fn=show_proxy_test_loading,
        outputs=test_result_ui,
    ).then(
        fn=test_proxy_connectivity,
        inputs=[https_proxy_ui, test_timeout_ui],
        outputs=test_result_ui,
    )

    serverchan_ui.submit(
        fn=inner_input_serverchan, inputs=serverchan_ui, outputs=serverchan_ui
    )
    serverchan3_ui.submit(
        fn=inner_input_serverchan3,
        inputs=serverchan3_ui,
        outputs=serverchan3_ui,
    )
    pushplus_ui.submit(fn=inner_input_pushplus, inputs=pushplus_ui, outputs=pushplus_ui)
    bark_ui.submit(fn=inner_input_bark, inputs=bark_ui, outputs=bark_ui)
    meow_ui.submit(fn=inner_input_meow, inputs=meow_ui, outputs=meow_ui)
    ntfy_ui.submit(fn=inner_input_ntfy, inputs=ntfy_ui, outputs=ntfy_ui)
    ntfy_username_ui.submit(
        fn=inner_input_ntfy_username,
        inputs=ntfy_username_ui,
        outputs=ntfy_username_ui,
    )
    ntfy_password_ui.submit(
        fn=inner_input_ntfy_password,
        inputs=ntfy_password_ui,
        outputs=ntfy_password_ui,
    )
    audio_path_ui.upload(
        fn=inner_input_audio_path,
        inputs=audio_path_ui,
        outputs=audio_path_ui,
    )
    show_random_message_ui.change(
        fn=update_hide_random_message,
        inputs=show_random_message_ui,
        outputs=show_random_message_ui,
    )
    hide_header_ui.change(
        fn=update_hide_header,
        inputs=hide_header_ui,
        outputs=[hide_header_ui, header_ui],
    )
    auto_fill_time_ui.change(
        fn=update_auto_fill_time,
        inputs=auto_fill_time_ui,
        outputs=auto_fill_time_ui,
    )
    notify_proxy_exhausted_ui.change(
        fn=update_notify_proxy_exhausted,
        inputs=notify_proxy_exhausted_ui,
        outputs=notify_proxy_exhausted_ui,
    )
    proxy_max_consecutive_failures_ui.change(
        fn=update_proxy_max_consecutive_failures,
        inputs=proxy_max_consecutive_failures_ui,
        outputs=proxy_max_consecutive_failures_ui,
    )
    proxy_cooldown_seconds_ui.change(
        fn=update_proxy_cooldown_seconds,
        inputs=proxy_cooldown_seconds_ui,
        outputs=proxy_cooldown_seconds_ui,
    )
    proxy_backoff_max_seconds_ui.change(
        fn=update_proxy_backoff_max_seconds,
        inputs=proxy_backoff_max_seconds_ui,
        outputs=proxy_backoff_max_seconds_ui,
    )
    show_qrcode_ui.change(
        fn=update_show_qrcode,
        inputs=show_qrcode_ui,
        outputs=show_qrcode_ui,
    )
    auto_open_payment_url_ui.change(
        fn=update_auto_open_payment_url,
        inputs=auto_open_payment_url_ui,
        outputs=auto_open_payment_url_ui,
    )
    proxy_assignment_strategy_ui.change(
        fn=update_proxy_assignment_strategy,
        inputs=proxy_assignment_strategy_ui,
        outputs=proxy_assignment_strategy_ui,
    )
    queue_concurrency_limit_ui.change(
        fn=update_queue_concurrency_limit,
        inputs=queue_concurrency_limit_ui,
        outputs=queue_concurrency_limit_ui,
    )
    log_level_ui.change(
        fn=update_log_level,
        inputs=log_level_ui,
        outputs=log_level_ui,
    )
    auto_cleanup_logs_ui.change(
        fn=update_auto_cleanup_logs,
        inputs=auto_cleanup_logs_ui,
        outputs=auto_cleanup_logs_ui,
    )
    log_retention_days_ui.change(
        fn=update_log_retention_days,
        inputs=log_retention_days_ui,
        outputs=log_retention_days_ui,
    )
    max_log_files_ui.change(
        fn=update_max_log_files,
        inputs=max_log_files_ui,
        outputs=max_log_files_ui,
    )
    max_run_dirs_ui.change(
        fn=update_max_run_dirs,
        inputs=max_run_dirs_ui,
        outputs=max_run_dirs_ui,
    )
    use_local_token_ui.change(
        fn=update_use_local_token,
        inputs=use_local_token_ui,
        outputs=use_local_token_ui,
    )
    request_interval_ui.change(
        fn=update_request_interval,
        inputs=request_interval_ui,
        outputs=request_interval_ui,
    )
    outer_loop_interval_ui.change(
        fn=update_outer_loop_interval,
        inputs=outer_loop_interval_ui,
        outputs=outer_loop_interval_ui,
    )
    create_retry_limit_ui.change(
        fn=update_create_retry_limit,
        inputs=create_retry_limit_ui,
        outputs=create_retry_limit_ui,
    )
    create_request_batch_size_ui.change(
        fn=update_create_request_batch_size,
        inputs=create_request_batch_size_ui,
        outputs=create_request_batch_size_ui,
    )
    test_audio_button.click(
        fn=test_terminal_audio,
        inputs=[],
        outputs=test_audio_result,
    )
    test_ntfy_button.click(
        fn=test_ntfy_connection,
        inputs=[],
        outputs=test_ntfy_result,
    )
    test_all_push_button.click(
        fn=test_all_push,
        inputs=[],
        outputs=test_push_result,
    )
