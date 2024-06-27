import importlib
import json
import threading
import time
import uuid
from datetime import datetime
from json import JSONDecodeError
from urllib.parse import urlencode, quote

import gradio as gr
import qrcode
from util.dynimport import bili_ticket_gt_python
from gradio import SelectData
from loguru import logger

from config import global_cookieManager, main_request
from geetest.CapSolverValidator import CapSolverValidator
from geetest.NormalValidator import NormalValidator
from geetest.RROCRValidator import RROCRValidator
from util.error import ERRNO_DICT, withTimeString
from util.order_qrcode import get_qrcode_url

ways = ["手动", "使用 rrocr", "使用 CapSolver"]
ways_detail = [NormalValidator(), RROCRValidator(), CapSolverValidator()]
if bili_ticket_gt_python is not None:
    tmp = importlib.import_module("geetest.AmorterValidator").AmorterValidator()
    ways_detail.append(tmp)
    ways.append("本地过验证码（Amorter提供）")


def format_dictionary_to_string(data):
    formatted_string_parts = []
    for key, value in data.items():
        if isinstance(value, list) or isinstance(value, dict):
            formatted_string_parts.append(
                f"{quote(key)}={quote(json.dumps(value, separators=(',', ':'), ensure_ascii=False))}"
            )
        else:
            formatted_string_parts.append(f"{quote(key)}={quote(str(value))}")

    formatted_string = "&".join(formatted_string_parts)
    return formatted_string


def go_tab():
    isRunning = False

    gr.Markdown("""
> **分享一下经验**
> - 抢票前，不要去提前抢还没有发售的票，会被b站封掉一段时间导致错过抢票的
> - 热门票要提前练习过验证码
> - 如果要使用自动定时抢，电脑的时间和b站的时间要一致
> - 使用不同的多个账号抢票 （可以每一个exe文件都使用不同的账号， 或者在使用这个程序的时候，手机使用其他的账号去抢）
> - 程序能保证用最快的速度发送订单请求，但是不保证这一次订单请求能够成功。所以不要完全依靠程序
> - 现在各个平台抢票和秒杀机制都是进抽签池抽签，网速快发请求多快在拥挤的时候基本上没有效果
> 此时就要看你有没有足够的设备和账号来提高中签率
> - 欢迎前往[discussions](https://github.com/mikumifa/biliTickerBuy/discussions) 分享你的经验
""")
    with gr.Column():
        with gr.Row(equal_height=True):
            upload_ui = gr.Files(label="上传多个配置文件，点击不同的配置文件可快速切换", file_count="multiple")
            ticket_ui = gr.TextArea(
                label="填入配置",
                info="再次填入配置信息 （不同版本的配置文件可能存在差异，升级版本时候不要偷懒，老版本的配置文件在新版本上可能出问题",
                interactive=True
            )
        gr.HTML(
            """<label for="datetime">选择抢票的时间</label><br> 
                <input type="datetime-local" id="datetime" name="datetime" step="1">""",
            label="选择抢票的时间",
            show_label=True,
        )

        def upload(filepath):
            try:
                with open(filepath[0], 'r', encoding="utf-8") as file:
                    content = file.read()
                return content
            except Exception as e:
                return str(e)

        def file_select_handler(select_data: SelectData, files):
            file_label = files[select_data.index]
            try:
                with open(file_label, 'r', encoding="utf-8") as file:
                    content = file.read()
                return content
            except Exception as e:
                return str(e)

        upload_ui.upload(fn=upload, inputs=upload_ui, outputs=ticket_ui)
        upload_ui.select(file_select_handler, upload_ui, ticket_ui)
        # 验证码选择

        way_select_ui = gr.Radio(ways, label="过验证码的方式", info="详细说明请前往 `训练你的验证码速度` 那一栏",
                                 type="index", value="手动")
        api_key_input_ui = gr.Textbox(label="填写你的api_key",
                                      value=global_cookieManager.get_config_value("appkey", ""),
                                      visible=False)
        select_way = 0

        def choose_option(way):
            nonlocal select_way
            select_way = way
            if ways_detail[select_way].need_api_key():
                return gr.update(visible=True)
            else:
                return gr.update(visible=False)

        way_select_ui.change(choose_option, inputs=way_select_ui, outputs=api_key_input_ui)
        with gr.Row():

            gt = ""
            challenge = ""
            geetest_validate = ""
            geetest_seccode = ""

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
    validate_con = threading.Condition()

    def start_go(tickets_info_str, time_start, interval, mode, total_attempts, api_key):
        nonlocal geetest_validate, geetest_seccode, gt, challenge, isRunning
        isRunning = True
        left_time = total_attempts

        while isRunning:
            try:
                if time_start != "":
                    try:
                        time_difference = (
                                datetime.strptime(time_start, "%Y-%m-%dT%H:%M:%S").timestamp()
                                - time.time()
                        )
                    except ValueError as e:
                        time_difference = (
                                datetime.strptime(time_start, "%Y-%m-%dT%H:%M").timestamp()
                                - time.time()
                        )
                    if time_difference > 0:
                        logger.info("等待中")
                        yield [
                            gr.update(value="等待中，如果想要停止等待，请重启程序", visible=True),
                            gr.update(visible=False),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                        ]
                        time.sleep(time_difference)  # 等待到指定的开始时间

                # 数据准备
                tickets_info = json.loads(tickets_info_str)
                _request = main_request
                token_payload = {
                    "count": tickets_info["count"],
                    "screen_id": tickets_info["screen_id"],
                    "order_type": 1,
                    "project_id": tickets_info["project_id"],
                    "sku_id": tickets_info["sku_id"],
                    "token": "",
                    "newRisk": True,
                }
                # 订单准备
                request_result_normal = _request.post(
                    url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                    data=token_payload,
                )
                request_result = request_result_normal.json()
                logger.info(f"1）订单准备")
                logger.info(f"请求头: {request_result_normal.headers} // 请求体: {request_result}")
                code = int(request_result["code"])
                # 完成验证码
                if code == -401:
                    # if True:
                    _url = "https://api.bilibili.com/x/gaia-vgate/v1/register"
                    _payload = urlencode(request_result["data"]["ga_data"]["riskParams"])
                    _data = _request.post(_url, _payload).json()
                    logger.info(
                        f"gaia-vgate: {_data}"
                    )
                    gt = _data["data"]["geetest"]["gt"]
                    challenge = _data["data"]["geetest"]["challenge"]
                    token = _data["data"]["token"]
                    # Fake test  START --------------------------------
                    # test_res = _request.get(
                    #     "https://passport.bilibili.com/x/passport-login/captcha?source=main_web"
                    # ).json()
                    # challenge = test_res["data"]["geetest"]["challenge"]
                    # gt = test_res["data"]["geetest"]["gt"]
                    # token = "123456"
                    # Fake test  END --------------------------------
                    geetest_validate = ""
                    geetest_seccode = ""
                    if ways_detail[select_way].have_gt_ui():
                        logger.info(f"Using {ways_detail[select_way]}, have gt ui")
                        yield [
                            gr.update(value=withTimeString("进行验证码验证"), visible=True),
                            gr.update(visible=True),
                            gr.update(),
                            gr.update(visible=True),
                            gr.update(value=gt),
                            gr.update(value=challenge),
                            gr.update(value=uuid.uuid1()),
                        ]

                    def run_validation():
                        nonlocal geetest_validate, geetest_seccode
                        try:
                            tmp = ways_detail[select_way].validate(appkey=api_key, gt=gt, challenge=challenge)
                        except Exception as e:
                            return
                        validate_con.acquire()
                        geetest_validate = tmp
                        geetest_seccode = geetest_validate + "|jordan"
                        validate_con.notify()
                        validate_con.release()

                    validate_con.acquire()
                    while geetest_validate == "" or geetest_seccode == "":
                        threading.Thread(target=run_validation).start()
                        yield [
                            gr.update(value=withTimeString(f"等待验证码完成， 使用{ways[select_way]}"), visible=True),
                            gr.update(visible=True),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                        ]
                        validate_con.wait()
                    validate_con.release()
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
                            gr.update(),
                        ]
                        continue
                    request_result = _request.post(
                        url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                        data=token_payload,
                    ).json()
                    logger.info(f"prepare: {request_result}")
                tickets_info["token"] = request_result["data"]["token"]
                # 金额通过手动计算，减少一次请求，提高速度
                # logger.info(f"2）核实订单，填写支付金额信息")
                # request_result = _request.get(
                #     url=f"https://show.bilibili.com/api/ticket/order/confirmInfo?token={tickets_info['token']}&voucher"
                #         f"=&project_id={tickets_info['project_id']}"
                # ).json()
                # logger.info(f"confirmInfo: {request_result}")
                # tickets_info["pay_money"] = request_result["data"]["pay_money"]
                logger.info(f"2）创建订单")
                tickets_info["timestamp"] = int(time.time()) * 100
                tickets_info["again"] = "true"
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
                    gr.update(),
                ]
                if errno == 0:
                    logger.info(f"3）抢票成功")
                    qrcode_url = get_qrcode_url(
                        _request,
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
            gr.update(),
        ]

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
        qr_image = gr.Image(label="使用微信或者支付宝扫码支付", visible=False, elem_classes="pay_qrcode")

    with gr.Row(visible=False) as gt_row:
        trigger = gr.Textbox(visible=False)
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
    trigger.change(
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
        nonlocal geetest_validate, geetest_seccode
        if "geetest_validate" in res and "geetest_seccode" in res:
            validate_con.acquire()
            geetest_validate = res["geetest_validate"]
            geetest_seccode = res["geetest_seccode"]
            validate_con.notify()
            validate_con.release()

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
        nonlocal isRunning
        isRunning = False

    go_btn.click(
        fn=start_go,
        inputs=[ticket_ui, time_tmp, interval_ui, mode_ui, total_attempts_ui, api_key_input_ui],
        outputs=[go_ui, stop_btn, qr_image, gt_row, gt_ui, challenge_ui, trigger],
    )
    stop_btn.click(
        fn=stop,
        inputs=None,
        outputs=None,
    )
