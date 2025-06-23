from argparse import Namespace


def ticker_cmd(args: Namespace):
    import gradio as gr
    from tab.go import go_tab
    from tab.problems import problems_tab
    from tab.settings import setting_tab
    from tab.train import train_tab
    from tab.log import log_tab

    from util.LogConfig import loguru_config
    from util import LOG_DIR

    loguru_config(LOG_DIR, "app.log", enable_console=True, file_colorize=False)
    header = """
    # B 站会员购抢票🌈

    ⚠️此项目完全开源免费 （[项目地址](https://github.com/mikumifa/biliTickerBuy)），切勿进行盈利，所造成的后果与本人无关。
    """

    with gr.Blocks(
        title="biliTickerBuy",
        head="""<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>""",
    ) as demo:
        gr.Markdown(header)
        with gr.Tab("生成配置"):
            setting_tab()
        with gr.Tab("操作抢票"):
            go_tab(demo)
        with gr.Tab("过码测试"):
            train_tab()
        with gr.Tab("项目说明"):
            problems_tab()
        with gr.Tab("日志查看"):
            log_tab()
    # 运行应用

    demo.launch(
        share=args.share,
        inbrowser=True,
        server_name=args.server_name,  # 必须监听所有 IP
        server_port=args.port,  # 使用 Cloud Run 提供的端口
    )
