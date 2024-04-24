from urllib.parse import urlencode
import gradio as gr

from config import cookies_config_path
from util.bili_request import BiliRequest


def train_tab():
    _request = BiliRequest(cookies_config_path=cookies_config_path)

    gr.Markdown("💪 在这里训练一下手过验证码的速度，提前演练一下")
    test_get_challenge_btn = gr.Button("开始测试")
    test_log = gr.JSON(label="测试结果（验证码过期是正常现象）")

    with gr.Row(visible=False) as test_gt_row:
        test_gt_html_start_btn = gr.Button("点击打开抢票验证码（请勿多点！！）")
        test_gt_html_finish_btn = gr.Button("完成验证码后点此此按钮")
        gr.HTML(
            value="""
                <div>
                    <label>如何点击无效说明，获取验证码失败，请勿多点</label>
                    <div id="captcha_test" />
                </div>
                """,
            label="验证码",
        )
    test_gt_ui = gr.Textbox(label="gt", visible=True)
    test_challenge_ui = gr.Textbox(label="challenge", visible=True)
    geetest_result = gr.JSON(label="validate")

    def test_get_challenge():
        global \
            test_challenge, \
            test_gt, \
            test_token, \
            test_csrf, \
            test_geetest_validate, \
            test_geetest_seccode
        test_res = _request.get(
            "https://passport.bilibili.com/x/passport-login/captcha?source=main_web"
        ).json()
        test_challenge = test_res["data"]["geetest"]["challenge"]
        test_gt = test_res["data"]["geetest"]["gt"]
        test_token = test_res["data"]["token"]
        test_csrf = _request.cookieManager.get_cookies_value("bili_jct")
        test_geetest_validate = ""
        test_geetest_seccode = ""
        return [
            gr.update(value=test_gt),  # test_gt_ui
            gr.update(value=test_challenge),  # test_challenge_ui
            gr.update(visible=True),  # test_gt_row
            gr.update(value="重新生成"),  # test_get_challenge_btn
        ]

    test_get_challenge_btn.click(
        fn=test_get_challenge,
        inputs=None,
        outputs=[test_gt_ui, test_challenge_ui, test_gt_row, test_get_challenge_btn],
    )
    test_gt_html_start_btn.click(
        fn=None,
        inputs=[test_gt_ui, test_challenge_ui],
        outputs=None,
        js="""
            (gt, challenge) => initGeetest({
                gt, challenge,
                offline: false,
                new_captcha: true,
                product: "popup",
                width: "300px",
                https: true
            }, function (test_captchaObj) {
                window.test_captchaObj = test_captchaObj;
                $('#captcha_test').empty();
                test_captchaObj.appendTo('#captcha_test');
            })
            """,
    )

    test_gt_html_finish_btn.click(
        fn=None,
        inputs=None,
        outputs=geetest_result,
        js="() => test_captchaObj.getValidate()",
    )
    def receive_geetest_result(res):
        global test_geetest_validate, test_geetest_seccode
        test_geetest_validate = res["geetest_validate"]
        test_geetest_seccode = res["geetest_seccode"]
    geetest_result.change(fn=receive_geetest_result, inputs=geetest_result)

    def test_doing():
        while test_geetest_validate == "" or test_geetest_seccode == "":
            continue
        _url = "https://api.bilibili.com/x/gaia-vgate/v1/validate"
        _payload = {
            "challenge": test_challenge,
            "token": test_token,
            "seccode": test_geetest_seccode,
            "csrf": test_csrf,
            "validate": test_geetest_validate,
        }
        test_data = _request.post(_url, urlencode(_payload))
        yield gr.update(value=test_data.json())

    test_gt_html_finish_btn.click(fn=test_doing, outputs=[test_log])
