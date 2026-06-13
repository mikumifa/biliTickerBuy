import gradio as gr
import html
import os
import signal
import subprocess
import time
from datetime import datetime

from util import GlobalStatusInstance
from util.log_web import build_log_view_url

TASK_STATUS_RUNNING = "运行中"
TASK_STATUS_STOPPED = "已主动终止"
TASK_STATUS_COMPLETED = "已完成"
TASK_STATUS_EXITED = "已结束"
TASK_COMPLETED_MARKER = "抢票完成后退出程序。。。。。"


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


def is_task_running(pid: int | None) -> bool:
    if not pid:
        return False
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
        if not entry.pid:
            continue
        if entry.status == TASK_STATUS_STOPPED:
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


def refresh_task_panel():
    return _refresh_token(), gr.update(visible=bool(visible_task_entries()))


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
        log_view_url = build_log_view_url(entry.log_file)
        status_class = _status_class(entry.status)
        file_link = (
            f'<a class="btb-task-link" href="{log_view_url}" target="_blank" rel="noopener noreferrer">'
            "查看日志"
            "</a>"
        )
        items.append(
            """
            <article class="btb-task-card {status_class}">
              <div class="btb-task-card__head">
                <div class="btb-task-card__title">{title}</div>
                <span class="btb-task-status {status_class}">{status}</span>
              </div>
              <div class="btb-task-card__meta">创建于 {created_at}</div>
              <div class="btb-task-card__actions">
                {file_link}
              </div>
            </article>
            """.format(
                created_at=html.escape(created_at),
                title=html.escape(entry.title),
                status=html.escape(entry.status),
                status_class=html.escape(status_class),
                file_link=file_link,
            )
        )
    items.append("</div>")
    return "".join(items)


def render_task_manager_panel(task_panel):
    refresh_token = gr.State(_refresh_token())
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
                        """.format(
                            title=html.escape(entry.title),
                            status=html.escape(entry.status),
                            status_class=html.escape(status_class),
                            created_at=html.escape(
                                datetime.fromtimestamp(entry.created_at).strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                            ),
                        )
                    )
                    with gr.Row(elem_classes="btb-task-card__actions"):
                        gr.HTML(
                            """
                            <a class="btb-task-link" href="{log_view_url}" target="_blank" rel="noopener noreferrer">查看日志</a>
                            """.format(
                                log_view_url=html.escape(
                                    build_log_view_url(entry.log_file)
                                )
                            )
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
        fn=refresh_task_panel,
        inputs=None,
        outputs=[refresh_token, task_panel],
    )
    return refresh_token


def log_tab():
    with gr.Column(elem_classes="btb-card btb-card-sky btb-layout-card") as task_panel:
        refresh_token = render_task_manager_panel(task_panel)
    return refresh_token, task_panel
