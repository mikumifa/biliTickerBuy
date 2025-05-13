import threading
import uuid
from urllib.parse import urlencode

import gradio as gr

from tab.go import ways_detail, ways
from util.config import main_request


def train_tab():
    gr.Markdown("""
> **补充**
>
> 在这里，你可以
> 1. 测试本地过验证码是否可行
>
""")
    _request = main_request
    # 验证码选择
    way_select_ui = gr.Radio(
        ways, label="验证码", info="过验证码的方式", type="index", value=ways[0]
    )
    api_key_input_ui = gr.Textbox(
        label="api_key",
        value=_request.cookieManager.get_config_value("appkey", ""),
        visible=False,
    )
    select_way = 0

    def choose_option(way):
        nonlocal select_way
        select_way = way
        # loguru.logger.info(way)
        validator = ways_detail[select_way]
        if validator.need_api_key():
            # rrocr
            return gr.update(visible=True)
        else:
            return gr.update(visible=False)

    way_select_ui.change(choose_option, inputs=way_select_ui, outputs=api_key_input_ui)

    test_get_challenge_btn = gr.Button("开始测试")
    test_log = gr.JSON(label="测试结果（显示验证码过期则说明成功）")
    with gr.Row(visible=False) as test_gt_row:
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
    trigger_ui = gr.Textbox(label="trigger", visible=False)

    geetest_result = gr.JSON(label="validate")
    validate_con = threading.Condition()
    test_challenge = ""
    test_gt = ""
    test_token = ""
    test_csrf = ""
    test_geetest_validate = ""
    test_geetest_seccode = ""

    def test_get_challenge(api_key):
        nonlocal \
            test_challenge, \
            test_gt, \
            test_token, \
            test_csrf, \
            test_geetest_validate, \
            test_geetest_seccode, \
            select_way
        test_res = _request.get(
            "https://passport.bilibili.com/x/passport-login/captcha?source=main_web"
        ).json()
        test_challenge = test_res["data"]["geetest"]["challenge"]
        test_gt = test_res["data"]["geetest"]["gt"]
        test_token = test_res["data"]["token"]
        test_csrf = _request.cookieManager.get_cookies_value("bili_jct")
        test_geetest_validate = ""
        test_geetest_seccode = ""
        validator = ways_detail[select_way]

        # Capture 不支持同时
        if validator.have_gt_ui():
            yield [
                gr.update(value=test_gt),  # test_gt_ui
                gr.update(value=test_challenge),  # test_challenge_ui
                gr.update(visible=True),  # test_gt_row
                gr.update(value="重新生成"),  # test_get_challenge_btn
                gr.update(value={}),
                gr.update(value=uuid.uuid1()),
            ]

        def run_validation():
            nonlocal test_geetest_validate, test_geetest_seccode
            try:
                tmp = validator.validate(gt=test_gt, challenge=test_challenge)
            except Exception as e:
                return
            validate_con.acquire()
            test_geetest_validate = tmp
            test_geetest_seccode = test_geetest_validate + "|jordan"
            validate_con.notify()
            validate_con.release()

        threading.Thread(target=run_validation).start()

        validate_con.acquire()
        while test_geetest_validate == "" or test_geetest_seccode == "":
            validate_con.wait()
        validate_con.release()

        _url = "https://api.bilibili.com/x/gaia-vgate/v1/validate"
        _payload = {
            "challenge": test_challenge,
            "token": test_token,
            "seccode": test_geetest_seccode,
            "csrf": test_csrf,
            "validate": test_geetest_validate,
        }
        test_data = _request.post(_url, urlencode(_payload))
        yield [
            gr.update(value=test_gt),  # test_gt_ui
            gr.update(value=test_challenge),  # test_challenge_ui
            gr.update(visible=False),  # test_gt_row
            gr.update(value="重新生成"),  # test_get_challenge_btn
            gr.update(value=test_data.json()),
            gr.update(),
        ]

    test_get_challenge_btn.click(
        fn=test_get_challenge,
        inputs=[api_key_input_ui],
        outputs=[
            test_gt_ui,
            test_challenge_ui,
            test_gt_row,
            test_get_challenge_btn,
            test_log,
            trigger_ui,
        ],
    )
    trigger_ui.change(
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
        nonlocal test_geetest_validate, test_geetest_seccode
        if "geetest_validate" in res and "geetest_seccode" in res:
            validate_con.acquire()
            test_geetest_validate = res["geetest_validate"]
            test_geetest_seccode = res["geetest_seccode"]
            validate_con.notify()
            validate_con.release()

    geetest_result.change(fn=receive_geetest_result, inputs=geetest_result)
