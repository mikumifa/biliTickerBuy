import gradio as gr
import os

LOG_PATH = (os.environ.get("LOG_PATH", "logs/app.log"))
def read_last_logs(n=1000):
    if not os.path.exists(LOG_PATH):
        return "No logs found."
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(lines[-n:])

def log_tab():
    log_textbox = gr.Textbox(label="最近日志", lines=20, interactive=False)
    refresh_btn = gr.Button("刷新日志")
    log_file_download = gr.File(label="下载完整日志", value=LOG_PATH, interactive=False)

    refresh_btn.click(fn=read_last_logs, inputs=None, outputs=log_textbox)
    timer = gr.Timer(5.0)
    timer.tick(fn=read_last_logs, outputs=log_textbox)