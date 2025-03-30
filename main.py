import argparse
import os.path

from loguru import logger

from const import BASE_DIR
from task.buy import buy


def main():
    log_file = os.path.join(BASE_DIR, "app.log")
    logger.add(log_file)
    parser = argparse.ArgumentParser(description="Ticket Purchase Tool or Gradio UI")
    subparsers = parser.add_subparsers(dest="command")
    # `--buy` 子命令
    buy_parser = subparsers.add_parser("buy", help="Start the ticket buying function")
    buy_parser.add_argument("tickets_info_str", type=str, help="Ticket information in string format.")
    buy_parser.add_argument("interval", type=int, help="Interval time.")
    buy_parser.add_argument("mode", type=int, help="Mode of operation.")
    buy_parser.add_argument("total_attempts", type=int, help="Total number of attempts.")
    buy_parser.add_argument("timeoffset", type=float, help="Time offset in seconds.")
    buy_parser.add_argument("--time_start", type=str, default="", help="Start time (optional")
    buy_parser.add_argument("--audio_path", type=str, default="", help="Path to audio file (optional).")
    buy_parser.add_argument("--pushplusToken", type=str, default="", help="PushPlus token (optional).")
    buy_parser.add_argument("--serverchanKey", type=str, default="", help="ServerChan key (optional).")
    buy_parser.add_argument("--phone", type=str, default="", help="Phone number (optional).")

    parser.add_argument("--port", type=int, default=7860, help="server port")
    parser.add_argument("--share", type=bool, default=False, help="create a public link")
    args = parser.parse_args()
    if args.command == "buy":
        buy(
            args.tickets_info_str, args.time_start, args.interval, args.mode,
            args.total_attempts, args.timeoffset, args.audio_path,
            args.pushplusToken, args.serverchanKey, args.phone
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

        short_js = """
        <script src="https://cdn.staticfile.org/jquery/1.10.2/jquery.min.js" rel="external nofollow"></script>
        <script src="https://static.geetest.com/static/js/gt.0.4.9.js"></script>
        """

        custom_css = """
        .pay_qrcode img {
          width: 300px !important;
          height: 300px !important;
          margin-top: 20px; /* 避免二维码头部的说明文字挡住二维码 */
        }
        """
        with gr.Blocks(head=short_js, css=custom_css) as demo:
            gr.Markdown(header)
            with gr.Tab("生成配置"):
                setting_tab()
            with gr.Tab("操作抢票"):
                go_tab()
            with gr.Tab("过码测试"):
                train_tab()
            with gr.Tab("项目说明"):
                problems_tab()

        # 运行应用
        print("点击下面的网址运行程序     ↓↓↓↓↓↓↓↓↓↓↓↓↓↓")
        demo.launch(share=args.share, inbrowser=True)


if __name__ == "__main__":
    main()
