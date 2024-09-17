import argparse
import os.path

import gradio as gr
from loguru import logger

from config import get_application_path, BASE_DIR
from tab.go import go_tab
from tab.login import login_tab
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860, help="server port")
    parser.add_argument("--share", type=bool, default=False, help="create a public link")
    args = parser.parse_args()
    log_file = os.path.join(BASE_DIR, "app.log")
    logger.add(log_file)
    with gr.Blocks(head=short_js, css=custom_css) as demo:
        gr.Markdown(header)
        with gr.Tab("生成配置"):
            setting_tab()
        with gr.Tab("操作抢票"):
            go_tab()
        with gr.Tab("过码测试"):
            train_tab()
        with gr.Tab("登录管理"):
            login_tab()
        with gr.Tab("项目说明"):
            problems_tab()

    # 运行应用
    print("点击下面的网址运行程序     ↓↓↓↓↓↓↓↓↓↓↓↓↓↓")
    demo.launch(share=args.share, inbrowser=True)
