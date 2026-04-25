import base64
import os
import threading
from argparse import Namespace

import gradio as gr
import loguru


def exit_app_ui():
    loguru.logger.info("程序退出")
    threading.Timer(2.0, lambda: os._exit(0)).start()
    gr.Info("程序将在弹出提示后退出")


def ticker_cmd(args: Namespace):
    from tab.go import go_tab
    from tab.log import log_tab
    from tab.problems import problems_tab
    from tab.settings import setting_tab
    from util import LOG_DIR
    from util.LogConfig import loguru_config

    loguru_config(LOG_DIR, "app.log", enable_console=True, file_colorize=False)
    icon_path = os.path.abspath(os.path.join("assets", "icon.ico"))
    icon_url = ""
    if os.path.exists(icon_path):
        with open(icon_path, "rb") as icon_file:
            icon_url = (
                "data:image/x-icon;base64,"
                + base64.b64encode(icon_file.read()).decode("ascii")
            )

    header = f"""
    <section class="btb-hero">
        <div class="btb-hero__eyebrow">BILI TICKER BUY</div>
        <div class="btb-hero__grid">
            <div>
                <h1>B 站会员购抢票工作台</h1>
                <p class="btb-hero__lead">
                    从登录、生成配置到定时开抢，按步骤完成准备，减少临场操作和信息遗漏。
                </p>
            </div>
            <div class="btb-hero__logo" aria-label="biliTickerBuy logo">
                <img class="btb-hero__logo-image" src="{icon_url}" alt="biliTickerBuy icon">
                
            </div>
        </div>
        <div class="btb-hero__notice">
            <span class="btb-hero__notice-mark">!</span>
            <span>
                此项目完全开源免费，
                <a href="https://github.com/mikumifa/biliTickerBuy" target="_blank">项目地址</a>。
                请勿用于盈利，使用后果自负。
            </span>
        </div>
    </section>
    """

    with gr.Blocks(
        title="biliTickerBuy",
        css="assets/style.css",
        head="""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&family=Noto+Serif+SC:wght@600&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
        """,
    ) as demo:
        with gr.Column(elem_classes="btb-app-shell"):
            gr.HTML(header)
            with gr.Tabs(elem_classes="btb-top-tabs"):
                with gr.Tab("生成配置"):
                    setting_tab()
                with gr.Tab("操作抢票"):
                    go_tab(demo)
                with gr.Tab("项目说明"):
                    problems_tab()
                with gr.Tab("日志查看"):
                    log_tab()

    is_docker = os.path.exists("/.dockerenv") or os.environ.get("BTB_DOCKER") == "1"
    demo.launch(
        share=args.share or is_docker,
        inbrowser=not is_docker,
        server_name=args.server_name,
        server_port=args.port,
    )
