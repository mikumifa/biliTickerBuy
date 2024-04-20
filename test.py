from urllib.parse import urlencode

import gradio as gr

from config import cookies_config_path
from util.BiliRequest import BiliRequest

_request = BiliRequest(cookies_config_path=cookies_config_path)
res = _request.get("https://passport.bilibili.com/x/passport-login/captcha?source=main_web").json()
challenge = res["data"]["geetest"]["challenge"]
gt = res["data"]["geetest"]["gt"]

token = res["data"]["token"]
_url = "https://api.bilibili.com/x/gaia-vgate/v1/validate"
csrf = _request.cookieManager.get_cookies_value("bili_jct")

short_js = """                <script
                        src="http://libs.baidu.com/jquery/1.10.2/jquery.min.js"
                        rel="external nofollow">
                </script>
                <script src="https://static.geetest.com/static/js/gt.0.4.9.js"></script>
       """
geetest_validate = ""
geetest_seccode = ""
with gr.Blocks(head=short_js) as demo:
    gt_html_btn = gr.Button("开始")
    gt_html_finish_btn = gr.Button("结束")
    print("gt,challenge", gt, challenge)
    gt_html_btn.click(fn=None, inputs=None, outputs=None,
                      js=f"""() => {{      initGeetest({{
                gt: "{gt}",
                challenge: "{challenge}",
                offline: false,
                new_captcha: true,
                product: "popup",
                width: "300px",
                https: true
            }}, function (captchaObj) {{
       window.captchaObj = captchaObj;
                captchaObj.appendTo('#captcha');
            }})}}""")
    geetest_validate_ui = gr.Textbox(visible=False)
    geetest_seccode_ui = gr.Textbox(visible=False)

    gt_html = gr.HTML(value="""
                       <div>
                       <label for="datetime">如何点击无效说明，获取验证码失败</label>
                        <div id="captcha">
                        </div>
                    </div>""", label="验证码")
    gt_ui = gr.Textbox(visible=False)
    challenge_ui = gr.Textbox(visible=False)

    gt_html_finish_btn.click(None, None, geetest_validate_ui,
                             js='() => {return captchaObj.getValidate().geetest_validate}')
    gt_html_finish_btn.click(None, None, geetest_seccode_ui,
                             js='() => {return captchaObj.getValidate().geetest_seccode}')


    def doing():
        while geetest_validate == "" or geetest_seccode == "":
            continue
        _payload = {
            "challenge": challenge,
            "token": token,
            "seccode": geetest_seccode,
            "csrf": csrf,
            "validate": geetest_validate
        }
        _data = _request.get(_url, urlencode(_payload))
        print(_data.json())


    gt_html_finish_btn.click(doing)


    def update_geetest_validate(x):
        global geetest_validate
        geetest_validate = x


    def update_geetest_seccode(x):
        global geetest_seccode
        geetest_seccode = x


    geetest_validate_ui.change(fn=update_geetest_validate, inputs=geetest_validate_ui, outputs=None)
    geetest_seccode_ui.change(fn=update_geetest_seccode, inputs=geetest_seccode_ui, outputs=None)
    # 运行应用
demo.launch()
