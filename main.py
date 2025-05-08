import argparse
import os.path
import uuid
import gradio_client
from loguru import logger

from task.buy import buy
from task.endpoint import start_heartbeat_thread


def main():

    parser = argparse.ArgumentParser(
        description="Ticket Purchase Tool or Gradio UI")
    subparsers = parser.add_subparsers(dest="command")
    # `--buy` 子命令
    buy_parser = subparsers.add_parser(
        "buy", help="Start the ticket buying function")
    buy_parser.add_argument("tickets_info_str", type=str,
                            help="Ticket information in string format.")
    buy_parser.add_argument("interval", type=int, help="Interval time.")
    buy_parser.add_argument("mode", type=int, help="Mode of operation.")
    buy_parser.add_argument("total_attempts", type=int,
                            help="Total number of attempts.")
    buy_parser.add_argument("timeoffset", type=float,
                            help="Time offset in seconds.")
    buy_parser.add_argument("--endpoint_url", type=str, help="endpoint_url.")
    buy_parser.add_argument("--time_start", type=str,
                            default="", help="Start time (optional")
    buy_parser.add_argument("--audio_path", type=str,
                            default="", help="Path to audio file (optional).")
    buy_parser.add_argument("--pushplusToken", type=str,
                            default="", help="PushPlus token (optional).")
    buy_parser.add_argument("--serverchanKey", type=str,
                            default="", help="ServerChan key (optional).")
    buy_parser.add_argument("--filename", type=str,
                            default="default", help="filename (optional).")

    parser.add_argument("--port", type=int, default=7860, help="server port")
    parser.add_argument("--share", type=bool, default=False,
                        help="create a public link")
    args = parser.parse_args()

    if args.command == "buy":
        logger.remove()
        from const import BASE_DIR
        os.makedirs(os.path.join(BASE_DIR, "log"), exist_ok=True)
        log_file = os.path.join(BASE_DIR, "log", f"{uuid.uuid1()}.log")
        logger.add(log_file, colorize=True,)
        import gradio as gr
        from pathlib import Path
        Path(log_file).touch(exist_ok=True)
        from gradio_log import Log
        filename_only = os.path.basename(args.filename)
        with gr.Blocks(title=f"{filename_only}", css=".xterm-screen {min-height: 70vh; max-height: 70vh} footer {visibility: hidden}") as demo:
            gr.Markdown(
                f"""
                # 当前抢票 {filename_only}
                > 你可以在这里查看程序的运行日志
                """
            )

            Log(log_file, dark=True, xterm_scrollback=5000,)

            def exit_program():
                print(f"{filename_only} ，关闭程序...")
                os._exit(0)

            btn = gr.Button("退出程序")
            btn.click(fn=exit_program)

        print(f"抢票日志路径： {log_file}")
        print(f"运行程序网址   ↓↓↓↓↓↓↓↓↓↓↓↓↓↓   {filename_only} ")
        demo.launch(share=False, inbrowser=True, prevent_thread_lock=True)
        client = gradio_client.Client(args.endpoint_url)
        assert demo.local_url
        start_heartbeat_thread(
            client, self_url=demo.local_url, to_url=args.endpoint_url, detail=filename_only)
        buy(
            args.tickets_info_str, args.time_start, args.interval, args.mode,
            args.total_attempts, args.timeoffset, args.audio_path,
            args.pushplusToken, args.serverchanKey
        )

    else:
        import gradio as gr
        from tab.go import go_tab
        from tab.problems import problems_tab
        from tab.settings import setting_tab
        from tab.train import train_tab

        header = """
        # B 站会员购抢票🌈

        ⚠️此项目完全开源免费 （[项目地址](https://github.com/mikumifa/biliTickerBuy)），切勿进行盈利，所造成的后果与本人无关。
        """

        from const import BASE_DIR
        log_file = os.path.join(BASE_DIR, "app.log")
        logger.add(log_file, colorize=True,)

        with gr.Blocks(title="biliTickerBuy") as demo:
            gr.Markdown(header)
            with gr.Tab("生成配置"):
                setting_tab()
            with gr.Tab("操作抢票"):
                go_tab(demo)
            with gr.Tab("过码测试"):
                train_tab()
            with gr.Tab("项目说明"):
                problems_tab()

        # 运行应用
        print("点击下面的网址运行程序     ↓↓↓↓↓↓↓↓↓↓↓↓↓↓")
        demo.launch(
            share=args.share, inbrowser=True)


if __name__ == "__main__":
    main()
