import json
import time
from datetime import datetime
from json import JSONDecodeError
from urllib.parse import urlencode

import gradio as gr
import qrcode
from loguru import logger

from common import format_dictionary_to_string
from config import cookies_config_path
from util.bili_request import BiliRequest
from util.error import ERRNO_DICT, withTimeString
from util.order_qrcode import get_qrcode_url

isRunning = False
gt = ""
challenge = ""
geetest_validate = ""
geetest_seccode = ""


def start_go(tickets_info_str, time_start, interval, mode, total_attempts):
    global isRunning, geetest_validate, geetest_seccode
    global gt
    global challenge
    isRunning = True
    left_time = total_attempts

    while isRunning:
        try:
            if time_start != "":
                time_difference = (
                        datetime.strptime(time_start, "%Y-%m-%dT%H:%M").timestamp()
                        - time.time()
                )
                if time_difference > 0:
                    logger.info("等待中")
                    yield [
                        gr.update(value="等待中,如果想要停止等待，请重启程序", visible=True),
                        gr.update(visible=False),
                        gr.update(),
                        gr.update(),
                        gr.update(),
                        gr.update(),
                    ]
                    time.sleep(time_difference)  # 等待到指定的开始时间
            tickets_info = json.loads(tickets_info_str)
            _request = BiliRequest(cookies_config_path=cookies_config_path)
            token_payload = {
                "count": tickets_info["count"],
                "screen_id": tickets_info["screen_id"],
                "order_type": 1,
                "project_id": tickets_info["project_id"],
                "sku_id": tickets_info["sku_id"],
                "token": "",
                "newRisk": True,
            }
            request_result_normal = _request.post(
                url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                data=token_payload,
            )
            request_result = request_result_normal.json()
            logger.info(f"prepare header: {request_result_normal.headers}")
            logger.info(f"prepare: {request_result}")
            code = int(request_result["code"])
            if code == -401:
                _url = "https://api.bilibili.com/x/gaia-vgate/v1/register"
                _payload = urlencode(request_result["data"]["ga_data"]["riskParams"])
                _data = _request.post(_url, _payload).json()
                logger.info(
                    f"gaia-vgate: {_data}"
                )
                gt = _data["data"]["geetest"]["gt"]
                challenge = _data["data"]["geetest"]["challenge"]
                token = _data["data"]["token"]
                # https://passport.bilibili.com/x/passport-login/captcha?source=main_web
                yield [
                    gr.update(value=withTimeString("进行验证码验证"), visible=True),
                    gr.update(visible=True),
                    gr.update(),
                    gr.update(visible=True),
                    gr.update(value=gt),
                    gr.update(value=challenge),
                ]
                while geetest_validate == "" or geetest_seccode == "":
                    continue
                logger.info(
                    f"geetest_validate: {geetest_validate},geetest_seccode: {geetest_seccode}"
                )
                _url = "https://api.bilibili.com/x/gaia-vgate/v1/validate"
                csrf = _request.cookieManager.get_cookies_value("bili_jct")
                _payload = {
                    "challenge": challenge,
                    "token": token,
                    "seccode": geetest_seccode,
                    "csrf": csrf,
                    "validate": geetest_validate,
                }
                _data = _request.post(_url, urlencode(_payload)).json()
                logger.info(f"validate: {_data}")
                geetest_validate = ""
                geetest_seccode = ""
                if _data["code"] == 0:
                    logger.info("极验 GeeTest 验证成功")
                else:
                    logger.info("极验 GeeTest 验证失败 {}", _data)
                    yield [
                        gr.update(value=withTimeString("极验 GeeTest 验证失败。重新验证"), visible=True),
                        gr.update(visible=True),
                        gr.update(),
                        gr.update(),
                        gr.update(),
                        gr.update(),
                    ]
                    continue
                request_result = _request.post(
                    url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                    data=token_payload,
                ).json()
                logger.info(f"prepare: {request_result}")
            tickets_info["token"] = request_result["data"]["token"]
            request_result = _request.get(
                url=f"https://show.bilibili.com/api/ticket/order/confirmInfo?token={tickets_info['token']}&voucher"
                    f"=&project_id={tickets_info['project_id']}"
            ).json()
            logger.info(f"confirmInfo: {request_result}")
            tickets_info["pay_money"] = request_result["data"]["pay_money"]
            tickets_info["timestamp"] = int(time.time()) * 100
            payload = format_dictionary_to_string(tickets_info)
            request_result = _request.post(
                url=f"https://show.bilibili.com/api/ticket/order/createV2?project_id={tickets_info['project_id']}",
                data=payload,
            ).json()
            errno = int(request_result["errno"])
            left_time_str = "无限" if mode == 0 else left_time
            logger.info(
                f'状态码: {errno}({ERRNO_DICT.get(errno, "未知错误码")}), 请求体: {request_result} 剩余次数: {left_time_str}'
            )
            yield [
                gr.update(
                    value=withTimeString(
                        f"正在抢票，具体情况查看终端控制台。\n剩余次数: {left_time_str}\n当前状态码: {errno} ({ERRNO_DICT.get(errno, '未知错误码')})"),
                    visible=True,
                ),
                gr.update(visible=True),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
            ]
            if errno == 0:
                qrcode_url = get_qrcode_url(
                    _request,
                    request_result["data"]["token"],
                    tickets_info["project_id"],
                    request_result["data"]["orderId"],
                )
                qr_gen = qrcode.QRCode()
                qr_gen.add_data(qrcode_url)
                qr_gen.make(fit=True)
                qr_gen_image = qr_gen.make_image()
                yield [
                    gr.update(value=withTimeString("生成付款二维码"), visible=True),
                    gr.update(visible=False),
                    gr.update(value=qr_gen_image.get_image(), visible=True),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                ]
                break
            if mode == 1:
                left_time -= 1
                if left_time <= 0:
                    break
        except JSONDecodeError as e:
            logger.error("配置文件格式错误")
            yield [
                gr.update(value=withTimeString("配置文件格式错误"), visible=True),
                gr.update(visible=True),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
            ]
        except Exception as e:
            logger.exception(e)
            yield [
                gr.update(value=withTimeString("有错误，具体查看控制台日志"), visible=True),
                gr.update(visible=True),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
            ]
        finally:
            time.sleep(interval / 1000.0)

    yield [
        gr.update(value="抢票结束", visible=True),
        gr.update(visible=False),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
    ]


def go_tab():
    with gr.Column():
        ticket_ui = gr.TextArea(
            label="填入配置", info="再次填入配置信息", interactive=True
        )
        gr.HTML(
            """<label for="datetime">选择抢票的时间</label><br> 
                <input type="datetime-local" id="datetime" name="datetime">""",
            label="选择抢票的时间",
            show_label=True,
        )

        with gr.Row():
            interval_ui = gr.Number(
                label="抢票间隔",
                value=1000,
                minimum=1,
                info="设置抢票任务之间的时间间隔（单位：毫秒），建议不要设置太小",
            )
            mode_ui = gr.Radio(
                label="抢票模式",
                choices=["无限", "有限"],
                value="无限",
                info="选择抢票的模式",
                type="index",
                interactive=True,
            )
            total_attempts_ui = gr.Number(
                label="总过次数",
                value=100,
                minimum=1,
                info="设置抢票的总次数",
                visible=False,
            )

        mode_ui.change(
            fn=lambda x: gr.update(visible=True)
            if x == 1
            else gr.update(visible=False),
            inputs=[mode_ui],
            outputs=total_attempts_ui,
        )
        with gr.Row():
            go_btn = gr.Button("开始抢票")
            stop_btn = gr.Button("停止", visible=False)

        with gr.Row():
            go_ui = gr.Textbox(
                info="此窗口为临时输出，具体请见控制台",
                label="输出信息",
                interactive=False,
                visible=False,
                show_copy_button=True,
                max_lines=10,

            )
            qr_image = gr.Image(label="使用微信或者支付宝扫码支付", visible=False)

        with gr.Row(visible=False) as gt_row:
            gt_html_btn = gr.Button("点击打开抢票验证码（请勿多点！！）")
            gt_html_finish_btn = gr.Button("完成验证码后点此此按钮")
            gr.HTML(
                value="""
                       <div>
                       <label>如何点击无效说明，获取验证码失败，请勿多点</label>
                        <div id="captcha">
                        </div>
                    </div>""",
                label="验证码",
            )
        geetest_result = gr.JSON(visible=False)
        time_tmp = gr.Textbox(visible=False)
        gt_ui = gr.Textbox(visible=False)
        challenge_ui = gr.Textbox(visible=False)
        gt_html_btn.click(
            fn=None,
            inputs=[gt_ui, challenge_ui],
            outputs=None,
            js="""
                (gt, challenge) => initGeetest({
                    gt, challenge,
                    offline: false,
                    new_captcha: true,
                    product: "popup",
                    width: "300px",
                    https: true
                }, function (captchaObj) {
                    window.captchaObj = captchaObj;
                    $('#captcha').empty();
                    captchaObj.appendTo('#captcha');
                })
                """,
        )

        def receive_geetest_result(res):
            global geetest_validate, geetest_seccode
            geetest_validate = res["geetest_validate"]
            geetest_seccode = res["geetest_seccode"]

        gt_html_finish_btn.click(
            fn=None,
            inputs=None,
            outputs=geetest_result,
            js="() => captchaObj.getValidate()",
        )
        gt_html_finish_btn.click(fn=receive_geetest_result, inputs=geetest_result)

        go_btn.click(
            fn=None,
            inputs=None,
            outputs=time_tmp,
            js='(x) => document.getElementById("datetime").value',
        )

        def stop():
            global isRunning
            isRunning = False
            return [
                gr.update(value="抢票结束", visible=True),
                gr.update(visible=False),
                gr.update(),
                gr.update(),
            ]

        go_btn.click(
            fn=start_go,
            inputs=[ticket_ui, time_tmp, interval_ui, mode_ui, total_attempts_ui],
            outputs=[go_ui, stop_btn, qr_image, gt_row, gt_ui, challenge_ui],
        )
        stop_btn.click(
            fn=stop,
            inputs=None,
            outputs=[go_ui, stop_btn, qr_image, gt_row],
        )
