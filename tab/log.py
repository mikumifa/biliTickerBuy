import ctypes
import gradio as gr
import html
import json
import os
import signal
import subprocess
import time
from datetime import datetime

from util import GlobalStatusInstance
from util import LOG_DIR
from util import log_file_name
from util.log_web import build_log_view_url
from util.task_markers import TASK_COMPLETED_MARKER, TASK_STOPPED_MARKER

TASK_STATUS_RUNNING = "运行中"
TASK_STATUS_STOPPED = "已主动结束"
TASK_STATUS_COMPLETED = "已完成"
TASK_STATUS_EXITED = "已结束"
OPEN_LOG_JS = """
(url) => {
    if (url) {
        window.open(url, "_blank", "noopener,noreferrer");
    }
}
"""
OPEN_PAYMENT_URLS_JS = """
(payload) => {
    if (!payload) {
        return;
    }
    let urls = [];
    try {
        urls = JSON.parse(payload);
    } catch (_err) {
        return;
    }
    const storageKey = "btb-opened-payment-urls";
    const opened = new Set(JSON.parse(window.localStorage.getItem(storageKey) || "[]"));
    let changed = false;
    for (const url of urls) {
        if (!url || opened.has(url)) {
            continue;
        }
        window.open(url, "_blank", "noopener,noreferrer");
        opened.add(url);
        changed = true;
    }
    if (changed) {
        window.localStorage.setItem(storageKey, JSON.stringify(Array.from(opened)));
    }
}
"""


def _status_class(status: str) -> str:
    mapping = {
        TASK_STATUS_RUNNING: "is-running",
        TASK_STATUS_COMPLETED: "is-completed",
        TASK_STATUS_STOPPED: "is-stopped",
        TASK_STATUS_EXITED: "is-exited",
    }
    return mapping.get(status, "is-exited")


def _refresh_token() -> int:
    return time.time_ns()


def build_main_log_card() -> str:
    return ""


def _render_log_path(path: str) -> str:
    return """
    <div class="btb-task-card__meta">
      日志路径
    </div>
    <div class="btb-task-card__path">
      <code>{path}</code>
    </div>
    """.format(path=html.escape(path))


def _render_log_view_action(path: str) -> str:
    return """
    <a class="btb-task-link btb-task-button" href="{log_view_url}" target="_blank" rel="noopener noreferrer">查看</a>
    """.format(log_view_url=html.escape(build_log_view_url(path)))


def _list_log_files() -> list[str]:
    try:
        items = [
            os.path.join(LOG_DIR, name)
            for name in os.listdir(LOG_DIR)
            if os.path.isfile(os.path.join(LOG_DIR, name))
        ]
    except OSError:
        return []
    return sorted(items, key=lambda path: os.path.getmtime(path), reverse=True)


def _find_task_entry_by_log_file(log_file: str):
    normalized = os.path.abspath(log_file)
    for entry in visible_task_entries():
        if os.path.abspath(entry.log_file) == normalized:
            return entry
    return None


def clear_log_files():
    log_files = _list_log_files()
    if not log_files:
        gr.Info("当前没有可清除的日志文件。")
        return refresh_log_panel()

    removed_paths: list[str] = []
    skipped_running: list[str] = []
    truncated_files: list[str] = []

    for log_file in log_files:
        entry = _find_task_entry_by_log_file(log_file)
        if entry is not None and entry.status == TASK_STATUS_RUNNING:
            skipped_running.append(log_file)
            continue

        try:
            if os.path.basename(log_file) == log_file_name:
                with open(log_file, "w", encoding="utf-8"):
                    pass
                truncated_files.append(log_file)
                continue
            os.remove(log_file)
            removed_paths.append(log_file)
        except OSError:
            continue

    if removed_paths:
        GlobalStatusInstance.remove_task_logs_by_paths(removed_paths)

    if removed_paths or truncated_files:
        message_parts: list[str] = []
        if removed_paths:
            message_parts.append(f"已删除 {len(removed_paths)} 个日志文件")
        if truncated_files:
            message_parts.append(
                f"已清空 {len(truncated_files)} 个当前使用中的应用日志文件"
            )
        if skipped_running:
            message_parts.append(f"跳过 {len(skipped_running)} 个运行中任务日志")
        gr.Info("，".join(message_parts) + "。")
    elif skipped_running:
        gr.Warning("存在运行中的任务日志，已跳过清除。")
    else:
        gr.Warning("日志清除失败，请检查文件权限。")

    return refresh_log_panel()


def is_task_running(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        synchronize = 0x00100000
        still_active = 259

        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information | synchronize,
            False,
            pid,
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            ):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    proc_stat_path = "/proc/{0}/stat".format(pid)
    if os.path.exists(proc_stat_path):
        try:
            with open(proc_stat_path, "r", encoding="utf-8") as handle:
                stat_fields = handle.read().split()
            if len(stat_fields) >= 3 and stat_fields[2] == "Z":
                return False
        except OSError:
            return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def terminate_task(pid: int) -> str:
    if not is_task_running(pid):
        return "任务进程已结束。"

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            return "停止任务进程失败。"

        deadline = time.time() + 3
        while time.time() < deadline:
            if not is_task_running(pid):
                return "已停止任务进程。"
            time.sleep(0.1)

        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            return "强制停止任务进程失败。"

        return "已发送停止任务请求"

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return "任务进程已结束。"

    deadline = time.time() + 3
    while time.time() < deadline:
        if not is_task_running(pid):
            return "已停止任务进程。"
        time.sleep(0.1)

    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return "已停止任务进程。"

    return "已强制停止任务进程。"


def sync_task_statuses() -> list:
    entries = GlobalStatusInstance.get_task_logs()
    for entry in entries:
        payment_qr_url = extract_payment_qr_url(entry.log_file)
        if payment_qr_url:
            entry.payment_qr_url = payment_qr_url
        if not entry.pid:
            continue
        if entry.status == TASK_STATUS_STOPPED:
            continue
        if log_contains_marker(entry.log_file, TASK_STOPPED_MARKER):
            GlobalStatusInstance.update_task_log_status(entry.pid, TASK_STATUS_STOPPED)
            continue
        if log_contains_marker(entry.log_file, TASK_COMPLETED_MARKER):
            GlobalStatusInstance.update_task_log_status(
                entry.pid, TASK_STATUS_COMPLETED
            )
            continue
        if is_task_running(entry.pid):
            GlobalStatusInstance.update_task_log_status(entry.pid, TASK_STATUS_RUNNING)
        elif entry.status == TASK_STATUS_RUNNING:
            GlobalStatusInstance.update_task_log_status(entry.pid, TASK_STATUS_EXITED)
    return GlobalStatusInstance.get_task_logs()


def visible_task_entries():
    return sync_task_statuses()


def log_contains_marker(log_file: str, marker: str) -> bool:
    try:
        with open(log_file, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 8192))
            content = handle.read().decode("utf-8", errors="replace")
        return marker in content
    except OSError:
        return False


def extract_payment_qr_url(log_file: str) -> str | None:
    try:
        with open(log_file, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 16384))
            content = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    marker = "PAYMENT_QR_URL="
    for line in reversed(content.splitlines()):
        if marker in line:
            return line.split(marker, 1)[1].strip()
    return None


def refresh_task_panel():
    return _refresh_token(), gr.update(visible=bool(visible_task_entries()))


def refresh_task_panel_with_payments():
    entries = visible_task_entries()
    urls = [entry.payment_qr_url for entry in entries if entry.payment_qr_url]
    return (
        _refresh_token(),
        gr.update(visible=bool(entries)),
        json.dumps(urls, ensure_ascii=False),
    )


def refresh_log_panel():
    return _refresh_token(), gr.update(visible=True)


def stop_task(pid: int):
    entry = GlobalStatusInstance.get_task_log(pid)
    message = terminate_task(pid)
    if entry and entry.log_file:
        append_stop_log(entry.log_file, entry.title, message)
    GlobalStatusInstance.update_task_log_status(pid, TASK_STATUS_STOPPED)
    if "强制" in message:
        gr.Warning(message)
    else:
        gr.Info(message)
    return refresh_task_panel()


def remove_task(pid: int):
    entry = GlobalStatusInstance.get_task_log(pid)
    if entry is None:
        gr.Warning("任务记录不存在。")
        return refresh_task_panel()

    if entry.status == TASK_STATUS_RUNNING:
        message = terminate_task(pid)
        if entry.log_file:
            append_stop_log(entry.log_file, entry.title, message)

    GlobalStatusInstance.remove_task_log(pid)
    gr.Info("已移除任务卡。")
    return refresh_task_panel()


def append_stop_log(log_file: str, title: str, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, "a", encoding="utf-8", errors="replace") as handle:
            handle.write("{0}\n".format(TASK_STOPPED_MARKER))
            handle.write(
                "\n[{0}] 已停止任务: {1} ({2})\n".format(timestamp, title, message)
            )
    except OSError:
        pass


def read_task_log_locations():
    entries = visible_task_entries()
    if not entries:
        return build_main_log_card()

    items: list[str] = [build_main_log_card(), '<div class="btb-task-grid">']
    for entry in entries:
        created_at = datetime.fromtimestamp(entry.created_at).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        status_class = _status_class(entry.status)
        items.append(
            """
            <article class="btb-task-card {status_class}">
              <div class="btb-task-card__head">
                <div class="btb-task-card__title">{title}</div>
                <span class="btb-task-status {status_class}">{status}</span>
              </div>
              <div class="btb-task-card__meta">创建于 {created_at}</div>
              {log_path}
              <div class="btb-task-card__actions">
                {log_action}
              </div>
            </article>
            """.format(
                created_at=html.escape(created_at),
                title=html.escape(entry.title),
                status=html.escape(entry.status),
                status_class=html.escape(status_class),
                log_path=_render_log_path(entry.log_file),
                log_action=_render_log_view_action(entry.log_file),
            )
        )
    items.append("</div>")
    return "".join(items)


def render_task_manager_panel(task_panel):
    refresh_token = gr.State(_refresh_token())
    payment_url_bus = gr.Textbox(visible=False)
    auto_refresh_timer = gr.Timer(value=2.0)
    with gr.Row(elem_classes="btb-task-toolbar-row"):
        gr.HTML("""<div class="btb-card-head"><div><h3>抢票任务管理</h3></div></div>""")
        refresh_btn = gr.Button(
            "刷新",
            elem_classes="btb-soft-button btb-task-button",
            scale=0,
            min_width=84,
        )

    @gr.render(inputs=refresh_token)
    def render_task_cards(_refresh_value):
        gr.HTML(build_main_log_card())
        with gr.Column(elem_classes="btb-task-grid"):
            for entry in visible_task_entries():
                status_class = _status_class(entry.status)
                with gr.Group(elem_classes=f"btb-task-card {status_class}"):
                    gr.HTML(
                        """
                        <div class="btb-task-card__head">
                          <div class="btb-task-card__title">{title}</div>
                          <span class="btb-task-status {status_class}">{status}</span>
                        </div>
                        <div class="btb-task-card__meta">创建于 {created_at}</div>
                        {log_path}
                        """.format(
                            title=html.escape(entry.title),
                            status=html.escape(entry.status),
                            status_class=html.escape(status_class),
                            created_at=html.escape(
                                datetime.fromtimestamp(entry.created_at).strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                            ),
                            log_path=_render_log_path(entry.log_file),
                        )
                    )
                    with gr.Row(elem_classes="btb-task-card__actions"):
                        view_btn = gr.Button(
                            "查看",
                            elem_classes="btb-soft-button btb-task-button btb-task-button--view",
                            scale=0,
                            min_width=84,
                        )
                        if entry.status == TASK_STATUS_RUNNING and entry.pid:
                            stop_btn = gr.Button(
                                "终止任务",
                                elem_classes="btb-soft-button btb-task-button btb-task-button--stop",
                                scale=0,
                                min_width=92,
                            )
                            stop_btn.click(
                                fn=lambda pid=entry.pid: stop_task(pid),
                                outputs=[refresh_token, task_panel],
                            )
                        view_btn.click(
                            fn=None,
                            inputs=gr.State(build_log_view_url(entry.log_file)),
                            outputs=None,
                            js=OPEN_LOG_JS,
                        )
                        remove_btn = gr.Button(
                            "移除",
                            elem_classes="btb-soft-button btb-task-button btb-task-button--remove",
                            scale=0,
                            min_width=84,
                        )
                        remove_btn.click(
                            fn=lambda pid=entry.pid: remove_task(pid),
                            outputs=[refresh_token, task_panel],
                        )

    refresh_btn.click(
        fn=refresh_task_panel_with_payments,
        inputs=None,
        outputs=[refresh_token, task_panel, payment_url_bus],
    )
    auto_refresh_timer.tick(
        fn=refresh_task_panel_with_payments,
        inputs=None,
        outputs=[refresh_token, task_panel, payment_url_bus],
        show_progress="hidden",
    )
    payment_url_bus.change(
        fn=None,
        inputs=payment_url_bus,
        outputs=None,
        js=OPEN_PAYMENT_URLS_JS,
    )
    return refresh_token


def log_tab():
    refresh_token = gr.State(_refresh_token())
    with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card") as task_panel:
        with gr.Row(elem_classes="btb-task-toolbar-row"):
            gr.HTML(
                """
                <div class="btb-card-head">
                    <div>
                        <h3>日志文件列表</h3>
                        <p>这里显示日志目录中的文件路径，可以自行去文件系统中查看。</p>
                    </div>
                </div>
                """
            )
            refresh_btn = gr.Button(
                "刷新",
                elem_classes="btb-soft-button btb-task-button",
                scale=0,
                min_width=84,
            )
            clear_btn = gr.Button(
                "一键清除",
                elem_classes="btb-soft-button btb-task-button btb-task-button--remove",
                scale=0,
                min_width=92,
            )

        @gr.render(inputs=refresh_token)
        def render_log_files(_refresh_value):
            log_files = _list_log_files()
            if not log_files:
                gr.HTML(
                    """
                    <div class="btb-card-note">
                        当前日志目录里还没有文件。
                    </div>
                    """
                )
                return

            with gr.Column(elem_classes="btb-task-grid"):
                for log_file in log_files:
                    entry = _find_task_entry_by_log_file(log_file)
                    title = (
                        entry.title if entry is not None else os.path.basename(log_file)
                    )
                    status = entry.status if entry is not None else "日志文件"
                    status_class = (
                        _status_class(entry.status)
                        if entry is not None
                        else "is-exited"
                    )
                    created_at = datetime.fromtimestamp(
                        os.path.getmtime(log_file)
                    ).strftime("%Y-%m-%d %H:%M:%S")

                    with gr.Group(elem_classes=f"btb-task-card {status_class}"):
                        gr.HTML(
                            """
                            <div class="btb-task-card__head">
                              <div class="btb-task-card__title">{title}</div>
                              <span class="btb-task-status {status_class}">{status}</span>
                            </div>
                            <div class="btb-task-card__meta">更新时间 {created_at}</div>
                            {log_path}
                            """.format(
                                title=html.escape(title),
                                status=html.escape(status),
                                status_class=html.escape(status_class),
                                created_at=html.escape(created_at),
                                log_path=_render_log_path(log_file),
                            )
                        )
                        view_btn = gr.Button(
                            "查看",
                            elem_classes="btb-soft-button btb-task-button btb-task-button--view",
                            scale=0,
                            min_width=84,
                        )
                        view_btn.click(
                            fn=None,
                            inputs=gr.State(build_log_view_url(log_file)),
                            outputs=None,
                            js=OPEN_LOG_JS,
                        )

        refresh_btn.click(
            fn=lambda: _refresh_token(),
            inputs=None,
            outputs=[refresh_token],
        )
        clear_btn.click(
            fn=clear_log_files,
            inputs=None,
            outputs=[refresh_token, task_panel],
        )

    return refresh_token, task_panel
