from loguru import logger

import gradio as gr

from tab.go import go_tab
from tab.settings import setting_tab
from tab.train import train_tab


header = """
# B 站会员购抢票🌈

⚠️此项目仅用于个人参考学习，切勿进行盈利，所造成的后果与本人无关。
"""

short_js = """
<script src="http://libs.baidu.com/jquery/1.10.2/jquery.min.js" rel="external nofollow"></script>
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
    logger.add("app.log")

    with gr.Blocks(head=short_js, css=custom_css) as demo:
        gr.Markdown(header)
        with gr.Tab("配置"):
            setting_tab()
        with gr.Tab("抢票"):
            go_tab()
        with gr.Tab("训练你的验证码速度"):
            train_tab()

    # 运行应用
    print("点击下面的网址运行程序     ↓↓↓↓↓↓↓↓↓↓↓↓↓↓")
    demo.launch()
