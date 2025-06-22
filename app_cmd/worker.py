from argparse import Namespace
import uuid

from loguru import logger
import uvicorn


from service.WorkerService import create_worker_app, stop_now_work
from task.endpoint import start_heartbeat_thread
from util import GlobalStatus


def get_port(url: str):
    from urllib.parse import urlparse

    parsed = urlparse(url)
    port = parsed.port
    return port


def worker_cmd(args: Namespace):
    from util.LogConfig import loguru_config
    from util import LOG_DIR

    log_file = loguru_config(
        LOG_DIR, f"{uuid.uuid1()}.log", enable_console=False, file_colorize=True
    )
    import gradio_client
    import gradio as gr
    from gradio_log import Log

    with gr.Blocks(
        head="""<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>""",
        title="Worker",
        fill_height=True,
    ) as demo:
        gr.Markdown(
            """
            你可以在这里查看程序的运行日志
            """
        )

        Log(
            log_file,
            dark=True,
            scale=1,
            xterm_log_level="info",
            xterm_scrollback=5000,
            elem_classes="h-full",
        )

        def exit_program():
            logger.info("停止当前任务...")
            stop_now_work()
            logger.info("已停止当前任务")

        btn = gr.Button("停止当前任务")
        btn.click(fn=exit_program)
    print(f"抢票日志路径： {log_file}")
    print("运行程序网址   ↓↓↓↓↓↓↓↓↓↓↓↓↓↓")
    app, _, _ = demo.launch(
        server_name=args.server_name,
        server_port=args.port,
        share=args.share,
        inbrowser=True,
        prevent_thread_lock=True,
    )

    # 心跳 server
    client = gradio_client.Client(args.master)
    assert demo.local_url
    GlobalStatus.nowTask = "none"
    start_heartbeat_thread(
        client,
        self_url=f"http://{args.self_ip}:{get_port(demo.local_url)}",
        to_url=args.master,
    )
    create_worker_app(app, args)
    uvicorn.run(app)
