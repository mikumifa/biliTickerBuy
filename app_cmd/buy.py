from argparse import Namespace
import os

from util import GlobalStatusInstance


def buy_cmd(args: Namespace):
    from util.LogConfig import loguru_config
    import uuid

    from util import LOG_DIR
    from task.buy import buy
    from loguru import logger

    def load_tickets_info(tickets_info: str) -> tuple[str, str | None]:
        config_path = os.path.expanduser(tickets_info)
        if os.path.isfile(config_path):
            logger.info(f"使用配置文件：{config_path}")
            try:
                with open(config_path, "r", encoding="utf-8") as config_file:
                    return config_file.read(), config_path
            except OSError as exc:
                raise SystemExit(f"读取配置文件失败: {exc}") from exc
        return tickets_info, None

    tickets_info, config_path = load_tickets_info(args.tickets_info)
    filename = os.path.basename(config_path) if config_path else "default"
    filename_only = os.path.basename(filename)
    if getattr(args, "web", False):
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
        GlobalStatusInstance.nowTask = filename_only
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
        tickets_info,
        args.time_start,
        args.interval,
        args.audio_path,
        args.pushplusToken,
        args.serverchanKey,
        args.barkToken,
        args.https_proxys,
        args.serverchan3ApiUrl,
        args.ntfy_url,
        args.ntfy_username,
        args.ntfy_password,
        not args.hide_random_message,
    )
    logger.info("抢票完成后退出程序。。。。。")
