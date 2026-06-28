import datetime
import html
import json
import os
import threading
import time
import uuid

import gradio as gr
from gradio import SelectData
from loguru import logger

from app_cmd.config.BuyConfig import BuyConfig
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
from util.Constant import (
    BEIJING_TZ,
    DEFAULT_MAX_LOG_FILES,
    DEFAULT_MAX_RUN_DIRS,
    DEFAULT_REQUEST_INTERVAL,
    GO_UPLOADED_FILES_STATE_KEY,
)


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
                value=None,
                minimum=1,
                info="默认抢票请求间隔（单位：毫秒）",
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
            time_service.now(),
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
        config: BuyConfig,
    ):
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read()
        filename_only = os.path.basename(filename)
        logger.info(f"启动 {filename_only}")
        log_file_path = _build_task_log_path(filename_only)
        logger.info(f"任务 {filename_only} 的日志文件：{log_file_path}")
        proc = buy_new_terminal(
            config=config.with_overrides(tickets_info=content),
            log_file_path=log_file_path,
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
        # 从配置文件加载
        buy_config = BuyConfig.from_config_db(
            time_start=time_start,
            interval=interval,
        )
        proxy_assignment_strategy = str(
            ConfigDB.get("proxyAssignmentStrategy") or "balanced"
        ).lower()
        queue_concurrency_limit = ConfigDB.get_as_int("queueConcurrencyLimit", 0)
        log_retention_days = buy_config.log_retention_days
        auto_cleanup_logs = ConfigDB.get("autoCleanupLogs")
        if auto_cleanup_logs is None:
            auto_cleanup_logs = True
        if auto_cleanup_logs:
            from util.Storage.CleanupUtil import cleanup_runtime_artifacts

            cleanup_runtime_artifacts(
                logs_dir=LOG_DIR,
                runs_dir=os.path.join(os.path.dirname(LOG_DIR), "btb_runs"),
                retention_days=log_retention_days,
                max_log_files=ConfigDB.get_as_int("maxLogFiles", DEFAULT_MAX_LOG_FILES),
                max_run_dirs=ConfigDB.get_as_int("maxRunDirs", DEFAULT_MAX_RUN_DIRS),
            )
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
                            config=buy_config.with_overrides(
                                https_proxys=proxy_slot,
                            ),
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
                config=buy_config.with_overrides(
                    https_proxys=",".join(assigned_proxies[assigned_proxies_next_idx]),
                ),
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

    def load_go_start_configs():
        return gr.update(
            value=ConfigDB.get_as_int("requestInterval", DEFAULT_REQUEST_INTERVAL)
        )

    return task_refresh_token, task_panel, load_go_start_configs, [interval_ui]
