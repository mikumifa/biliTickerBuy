from argparse import Namespace

from util import GlobalStatus


def buy_cmd(args: Namespace):
    from util.LogConfig import loguru_config
    import uuid

    from util import LOG_DIR
    import os
    from task.buy import buy
    from loguru import logger

    filename_only = os.path.basename(args.filename)
    logger.info(f"模式：{args.terminal_ui}")
    if args.terminal_ui == "网页":
        log_file = loguru_config(
            LOG_DIR, f"{uuid.uuid1()}.log", enable_console=False, file_colorize=True
        )
        from task.endpoint import start_heartbeat_thread
        import gradio_client
        import gradio as gr
        from gradio_log import Log

        with gr.Blocks(
            head="""<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>""",
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

            btn = gr.Button("关闭程序")
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
        GlobalStatus.nowTask = filename_only
        start_heartbeat_thread(
            client,
            self_url=demo.local_url,
            to_url=args.endpoint_url,
        )
    else:
        log_file = loguru_config(
            LOG_DIR, f"{uuid.uuid1()}.log", enable_console=True, file_colorize=True
        )
    buy(
        args.tickets_info_str,
        args.time_start,
        args.interval,
        args.mode,
        args.total_attempts,
        args.audio_path,
        args.pushplusToken,
        args.serverchanKey,
        args.barkToken,
        args.https_proxys,
        args.ntfy_url,
        args.ntfy_username,
        args.ntfy_password,
        not args.hide_random_message,
    )
    logger.info("抢票完成后退出程序。。。。。")
