import threading
from urllib.parse import urlencode

import gradio as gr

from config import cookies_config_path
from tab.go import ways_detail, ways
from util.bili_request import BiliRequest


def train_tab():
    gr.Markdown("""
> **补充**
>
> 在这里，你可以
> 1. 提前知道抢票时候验证码的过程
> 2. 训练验证码，提高验证码速度
>
""")
    _request = BiliRequest(cookies_config_path=cookies_config_path)

    gr.Markdown("💪 在这里训练一下手过验证码的速度，提前演练一下")

    gr.Markdown("""
    

    
| 过码方式           | 使用说明                                                     |
| ------------------ | ------------------------------------------------------------ |
| 手动               | 自己过，速度取决于自己，过程看项目的readme.md的GIF           |
| 使用接码网站 rrocr | **支持**手动和人工同时使用 <br /> rrocr 提供的 http://www.rrocr.com<br /> 能过验证码，但是抢票没有测试，慎用 <br /> 需要购买对应的key，速度比手动快，价格 一次大概一分钱<br /> |
| 使用接码网站 CapSolve | **不支持**手动和人工同时使用 <br />  CapSolver的过码方式<br />https://www.capsolver.com/zh <br />https://docs.capsolver.com/guide/captcha/Geetest.html|
| .....              | 欢迎Discussion补充                                                     |
    
    """)

    # 验证码选择
    way_select_ui = gr.Radio(ways, label="验证码", info="过验证码的方式", type="index", value="手动")
    api_key_input_ui = gr.Textbox(label="api_key", value=_request.cookieManager.get_config_value("appkey", ""),
                                  visible=False)
    select_way = 0

    def choose_option(way):
        global select_way
        select_way = way
        # loguru.logger.info(way)
        if way == 0:
            # rrocr
            return gr.update(visible=False)
        else:
            return gr.update(visible=True)

    way_select_ui.change(choose_option, inputs=way_select_ui, outputs=api_key_input_ui)

    test_get_challenge_btn = gr.Button("开始测试")
    test_log = gr.JSON(label="测试结果（验证码过期是正常现象）")
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

    def test_get_challenge(api_key):
        global \
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

        try:
            # Capture 不支持同时
            if select_way != 2:
                yield [
                    gr.update(value=test_gt),  # test_gt_ui
                    gr.update(value=test_challenge),  # test_challenge_ui
                    gr.update(visible=True),  # test_gt_row
                    gr.update(value="重新生成"),  # test_get_challenge_btn
                    gr.update(),
                    gr.update(value="hello")
                ]
            if select_way != 0:
                def run_validation():
                    global test_geetest_validate, test_geetest_seccode
                    validator = ways_detail[select_way]
                    test_geetest_validate = validator.validate(appkey=api_key, gt=test_gt, challenge=test_challenge)
                    test_geetest_seccode = test_geetest_validate + "|jordan"

                threading.Thread(target=run_validation).start()
        except NameError as err:
            pass
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
        yield [
            gr.update(value=test_gt),  # test_gt_ui
            gr.update(value=test_challenge),  # test_challenge_ui
            gr.update(visible=False),  # test_gt_row
            gr.update(value="重新生成"),  # test_get_challenge_btn
            gr.update(value=test_data.json()),
            gr.update()
        ]

    test_get_challenge_btn.click(
        fn=test_get_challenge,
        inputs=[api_key_input_ui],
        outputs=[test_gt_ui, test_challenge_ui, test_gt_row, test_get_challenge_btn, test_log, trigger_ui],
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
        global test_geetest_validate, test_geetest_seccode
        test_geetest_validate = res["geetest_validate"]
        test_geetest_seccode = res["geetest_seccode"]

    geetest_result.change(fn=receive_geetest_result, inputs=geetest_result)
