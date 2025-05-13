from argparse import Namespace

from util import LOG_DIR


def buy_cmd(args: Namespace):
    from util.LogConfig import loguru_config

    log_file = loguru_config(
        LOG_DIR, "app.log", enable_console=False, file_colorize=True
    )

    import os.path
    import gradio_client
    from task.buy import buy
    from task.endpoint import start_heartbeat_thread
    import os

    import gradio as gr
    from gradio_log import Log

    filename_only = os.path.basename(args.filename)
    with gr.Blocks(
        head="""
                    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
                    """,
        title=f"{filename_only}",
        fill_height=True,
    ) as demo:
        gr.Markdown(
            f"""
            # 当前抢票 {filename_only}
            > 你可以在这里查看程序的运行日志
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
            print(f"{filename_only} ，关闭程序...")
            os._exit(0)

        btn = gr.Button("退出程序")
        btn.click(fn=exit_program)

    print(f"抢票日志路径： {log_file}")
    print(f"运行程序网址   ↓↓↓↓↓↓↓↓↓↓↓↓↓↓   {filename_only} ")
    demo.launch(
        server_name=args.server_name,
        server_port=args.port,
        share=args.share,
        inbrowser=True,
        prevent_thread_lock=True,
    )
    client = gradio_client.Client(args.endpoint_url)
    assert demo.local_url
    start_heartbeat_thread(
        client,
        self_url=demo.local_url,
        to_url=args.endpoint_url,
        detail=filename_only,
    )
    buy(
        args.tickets_info_str,
        args.time_start,
        args.interval,
        args.mode,
        args.total_attempts,
        args.timeoffset,
        args.audio_path,
        args.pushplusToken,
        args.serverchanKey,
    )
