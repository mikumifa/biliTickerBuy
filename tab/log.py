import gradio as gr
import os

from util import GlobalStatusInstance, LOG_DIR


def read_last_logs(n=1000):
    app_log_paht = os.path.join(LOG_DIR, "app.log")
    if not os.path.exists(app_log_paht):
        return "No logs found."
    with open(app_log_paht, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(lines[-n:])


def read_task_log_locations():
    entries = GlobalStatusInstance.get_task_logs()
    if not entries:
        return "暂无已启动的抢票任务日志记录。"

    lines: list[str] = []
    for entry in entries:
        log_dir = os.path.dirname(entry.log_file)
        pid_text = str(entry.pid) if entry.pid is not None else "未知"
        lines.append(
            "\n".join(
                [
                    f"任务: {entry.title}",
                    f"模式: {entry.mode}",
                    f"PID: {pid_text}",
                    f"日志文件: {entry.log_file}",
                    f"日志目录: {log_dir}",
                ]
            )
        )
    return "\n\n".join(lines)


def log_tab():
    task_log_textbox = gr.Textbox(
        label="抢票窗口日志位置",
        lines=12,
        interactive=False,
        elem_classes="log",
    )
    log_textbox = gr.Textbox(
        label="最近日志", lines=20, interactive=False, elem_classes="log"
    )
    refresh_btn = gr.Button("刷新日志")
    gr.File(
        label="下载完整日志", value=os.path.join(LOG_DIR, "app.log"), interactive=False
    )

    refresh_btn.click(
        fn=lambda: [read_task_log_locations(), read_last_logs()],
        inputs=None,
        outputs=[task_log_textbox, log_textbox],
    )
    timer = gr.Timer(5.0)
    timer.tick(
        fn=lambda: [read_task_log_locations(), read_last_logs()],
        outputs=[task_log_textbox, log_textbox],
    )
