import gradio as gr
import html
import os
from datetime import datetime

from util import GlobalStatusInstance, LOG_DIR
from util.log_web import build_log_view_url


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
        return '<div class="btb-card-note">暂无已启动的抢票任务日志记录。</div>'

    items: list[str] = []
    for entry in entries:
        created_at = datetime.fromtimestamp(entry.created_at).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        file_link = (
            f'<a href="{build_log_view_url(entry.log_file)}" target="_blank" rel="noopener noreferrer">'
            f"{html.escape(entry.log_file)}"
            "</a>"
        )
        items.append(
            """
            <div style="padding:8px 0;border-bottom:1px solid #e2e8f0;line-height:1.6;">
              <div><strong>创建时间：</strong>{created_at}</div>
              <div><strong>配置文件：</strong>{title}</div>
              <div><strong>日志路径：</strong>{file_link}</div>
            </div>
            """.format(
                created_at=html.escape(created_at),
                title=html.escape(entry.title),
                file_link=file_link,
            )
        )
    return "".join(items)


def log_tab():
    task_log_textbox = gr.HTML(
        label="抢票窗口日志位置",
        value=read_task_log_locations(),
    )
    log_textbox = gr.Textbox(
        label="最近日志",
        lines=20,
        max_lines=20,
        interactive=False,
        elem_id="btb-log-output",
        elem_classes="log",
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
