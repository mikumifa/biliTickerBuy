import importlib
import json
import os
import threading
import time
import uuid
from datetime import datetime
from json import JSONDecodeError
from urllib.parse import urlencode, quote

import gradio as gr
import qrcode
import retry
from gradio import SelectData
from loguru import logger
from requests import HTTPError, RequestException

from config import global_cookieManager, main_request, configDB, time_service
from geetest.CapSolverValidator import CapSolverValidator
from geetest.NormalValidator import NormalValidator
from geetest.RROCRValidator import RROCRValidator
from util import PushPlusUtil
from util import ServerChanUtil
from util.dynimport import bili_ticket_gt_python
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
> - 欢迎前往 [discussions](https://github.com/mikumifa/biliTickerBuy/discussions) 分享你的经验
""")
    with gr.Column():
        gr.Markdown(
            """
            ### 上传或填入你要抢票票种的配置信息
            """
        )
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

        # 手动设置/更新时间偏差
        with gr.Accordion(label='手动设置/更新时间偏差', open=False):
            time_diff_ui = gr.Number(label="当前脚本时间偏差 (单位: ms)",
                                     info="你可以在这里手动输入时间偏差, 或点击下面按钮自动更新当前时间偏差。正值将推迟相应时间开始抢票, 负值将提前相应时间开始抢票。",
                                     value=format(time_service.get_timeoffset() * 1000, '.2f'))
            refresh_time_ui = gr.Button(value="点击自动更新时间偏差")
            refresh_time_ui.click(fn=lambda: format(float(time_service.compute_timeoffset()) * 1000, '.2f'),
                                  inputs=None, outputs=time_diff_ui)
            time_diff_ui.change(fn=lambda x: time_service.set_timeoffset(format(float(x) / 1000, '.5f')),
                                inputs=time_diff_ui, outputs=None)

        # 验证码选择

        way_select_ui = gr.Radio(ways, label="过验证码的方式", info="详细说明请前往 `训练你的验证码速度` 那一栏",
                                 type="index", value="手动")
        api_key_input_ui = gr.Textbox(label="填写你的api_key",
                                      value=global_cookieManager.get_config_value("appkey", ""),
                                      visible=False)
        phone_gate_ui = gr.Textbox(label="填写你的当前账号所绑定的手机号",
                                   info="可能会出现手机号验证",
                                   value=global_cookieManager.get_config_value("phone", ""))

        # 暂不可用
        with gr.Accordion("验证码预填设置[可选]", open=False, visible=False):
            gr.Markdown(
                """
                ### 请注意阅读下方注意事项
                - 在这里, 你可以上传或者填入要抢票的票仓下其他已开票/已售罄的票种配置文件(填入其他票仓的配置文件是无效的)来辅助抢票。脚本会使用该配置文件提前请求验证码, 降低抢票时遇到验证码的概率
                - 请注意: 你需要在配置选项卡下, 选择你要抢的票仓中**其它已售罄或者已开票还未售罄**的票种来生成配置文件填入这里, 选择不可售的票种配置文件填入这里**可能会被风控**
                - 你可以通过修改下方的"验证码提前预填时间", 来配置提前多长时间开始预填验证码
                - 在距抢票开始时间不足30秒时, 为避免影响正常开票时抢票, 验证码预填功能将不会启用
                - 如不需要使用验证码预填功能, 此处请留空
                """
            )
            with gr.Row(equal_height=True):
                authcode_prepare_file_ui = gr.Files(label="上传多个配置文件，点击不同的配置文件可快速切换",
                                                    file_count="multiple"
                                                    )
                authcode_prepare_text_ui = gr.TextArea(
                    label="填入配置",
                    info="再次填入配置信息。不同版本的配置文件可能存在差异，升级版本时候不要偷懒，老版本的配置文件在新版本上可能出问题",
                    interactive=True
                )
            authcode_preorder_time_ui = gr.Number(label="验证码提前预填时间(单位: 秒)",
                                                  info="设置在正式抢票之前多秒开始预填验证码, 最小值为30秒",
                                                  minimum=30,
                                                  value=180)
            authcode_prepare_file_ui.upload(fn=upload, inputs=authcode_prepare_file_ui,
                                            outputs=authcode_prepare_text_ui)
            authcode_prepare_file_ui.select(fn=file_select_handler, inputs=authcode_prepare_file_ui,
                                            outputs=authcode_prepare_text_ui)

        with gr.Accordion(label='配置抢票成功声音提醒[可选]', open=False):
            with gr.Row():
                gr.Markdown("""
                目前只支持wav格式，其他格式请自行转换 https://www.freeconvert.com/mp3-to-wav
                或者下载ffmpeg （这个自行网络上搜索，下载比较麻烦
                """)
                audio_path_ui = gr.Audio(
                    label="上传提示声音[只支持格式wav]", type="filepath", loop=True)

        def input_phone(_phone):
            global_cookieManager.set_config_value("phone", _phone)

        phone_gate_ui.change(fn=input_phone, inputs=phone_gate_ui, outputs=None)
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
                value=300,
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

    def start_go(tickets_info_str, authcode_prepare_str, authcode_preorder_time, time_start, interval, mode,
                 total_attempts, api_key, audio_path):
        nonlocal geetest_validate, geetest_seccode, gt, challenge, isRunning
        isRunning = True

        left_time = total_attempts
        yield [
            gr.update(value=withTimeString("详细信息见控制台"), visible=True),
            gr.update(visible=True),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
        ]
        while isRunning:
            try:
                if time_start != "":
                    logger.info("0) 等待开始时间")
                    timeoffset = time_service.get_timeoffset()
                    logger.info("时间偏差已被设置为: " + str(timeoffset) + 's')
                    authcode_prepare_flag = 0  # 标记是否已进行预填, 避免重复预填
                    while isRunning:
                        try:
                            time_difference = (
                                    datetime.strptime(time_start, "%Y-%m-%dT%H:%M:%S").timestamp()
                                    - time.time() + timeoffset
                            )
                        except ValueError as e:
                            time_difference = (
                                    datetime.strptime(time_start, "%Y-%m-%dT%H:%M").timestamp()
                                    - time.time() + timeoffset
                            )
                        if time_difference > 0:
                            if time_difference > 5:
                                # 抢票验证码预填
                                if authcode_preorder_time >= time_difference > 30 and authcode_prepare_str != "" and authcode_prepare_flag == 0:
                                    logger.info("开始进行预填验证码, 设定的提前预填时间为: " + str(
                                        authcode_preorder_time) + "秒")
                                    yield [
                                        gr.update(
                                            value=withTimeString("开始进行预填验证码, 如选择手动模式请注意验证码弹窗。"),
                                            visible=True),
                                        gr.update(visible=True),
                                        gr.update(),
                                        gr.update(),
                                        gr.update(),
                                        gr.update(),
                                        gr.update(),
                                        gr.update(),
                                    ]
                                    attempt_times = 2  # 为避免错过开票时间, 最多尝试两次预填
                                    while attempt_times > 0:
                                        # ---------验证码预填 BEGIN--------- #
                                        # 验证码预填只需通过prepare拿到token即可, 无需尝试提交订单
                                        # 数据准备
                                        tickets_info = json.loads(authcode_prepare_str)
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
                                        logger.info(f"预填验证码_订单准备")
                                        request_result_normal = _request.post(
                                            url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                                            data=token_payload,
                                        )
                                        request_result = request_result_normal.json()
                                        logger.info(
                                            f"请求头: {request_result_normal.headers} // 请求体: {request_result}")
                                        code = int(request_result["code"])
                                        # 完成验证码
                                        if code == -401:
                                            # if True:
                                            _url = "https://api.bilibili.com/x/gaia-vgate/v1/register"
                                            _payload = urlencode(request_result["data"]["ga_data"]["riskParams"])
                                            _data = _request.post(_url, _payload).json()
                                            logger.info(
                                                f"验证码请求: {_data}"
                                            )
                                            csrf = _request.cookieManager.get_cookies_value("bili_jct")
                                            token = _data["data"]["token"]
                                            if _data["data"]["type"] == "geetest":
                                                gt = _data["data"]["geetest"]["gt"]
                                                challenge = _data["data"]["geetest"]["challenge"]
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
                                                        gr.update(),
                                                        gr.update(value=uuid.uuid1()),
                                                    ]

                                                def run_validation():
                                                    nonlocal geetest_validate, geetest_seccode
                                                    try:
                                                        tmp = ways_detail[select_way].validate(appkey=api_key, gt=gt,
                                                                                               challenge=challenge)
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
                                                        gr.update(value=withTimeString(
                                                            f"等待验证码完成， 使用{ways[select_way]}"),
                                                            visible=True),
                                                        gr.update(visible=True),
                                                        gr.update(),
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
                                                _payload = {
                                                    "challenge": challenge,
                                                    "token": token,
                                                    "seccode": geetest_seccode,
                                                    "csrf": csrf,
                                                    "validate": geetest_validate,
                                                }
                                                _data = _request.post(_url, urlencode(_payload)).json()
                                            elif _data["data"]["type"] == "phone":
                                                _payload = {
                                                    "code": global_cookieManager.get_config_value("phone", ""),
                                                    "csrf": csrf,
                                                    "token": token,
                                                }
                                                _data = _request.post(_url, urlencode(_payload)).json()
                                            else:
                                                logger.warning("这个一个程序无法应对的验证码，脚本无法处理")
                                                break
                                            logger.info(f"validate: {_data}")
                                            geetest_validate = ""
                                            geetest_seccode = ""
                                            if _data["code"] == 0:
                                                logger.info('预填验证码成功, 等待开票')
                                                break
                                            else:
                                                logger.warning("预填验证码失败 {}", _data)
                                                yield [
                                                    gr.update(value=withTimeString("预填验证码失败。重新验证"),
                                                              visible=True),
                                                    gr.update(visible=True),
                                                    gr.update(),
                                                    gr.update(),
                                                    gr.update(),
                                                    gr.update(),
                                                    gr.update(),
                                                    gr.update(),
                                                ]
                                                attempt_times += 1
                                                time.sleep(1)  # 休息1秒, 避免触发风控
                                        if code == 0:
                                            logger.info("未出现验证码, IP可能已在白名单中, 跳过验证码预填")
                                            break
                                    # ---------验证码预填 END--------- #
                                    authcode_prepare_flag = 1
                                # 剩余时间大于5秒时, 每秒渲染一次页面, 渲染后重新计算剩余开票时间, 不会导致剩余时间计算误差累积
                                else:
                                    yield [
                                        gr.update(value="等待中，剩余等待时间: " + (str(int(
                                            time_difference)) + '秒') if time_difference > 6 else '即将开抢',
                                                  visible=True),
                                        gr.update(visible=True),
                                        gr.update(),
                                        gr.update(),
                                        gr.update(),
                                        gr.update(),
                                        gr.update(),
                                        gr.update(),
                                    ]
                                    time.sleep(1)
                            else:
                                # 准备倒计时开票, 不再渲染页面, 确保计时准确
                                # 使用 time.perf_counter() 方法实现高精度计时, 但可能会占用一定的CPU资源
                                start_time = time.perf_counter()
                                end_time = start_time + time_difference
                                current_time = start_time
                                while current_time < end_time:
                                    current_time = time.perf_counter()
                                break
                            if not isRunning:
                                # 停止定时抢票
                                yield [
                                    gr.update(value='手动停止定时抢票', visible=True),
                                    gr.update(visible=True),
                                    gr.update(),
                                    gr.update(),
                                    gr.update(),
                                    gr.update(),
                                    gr.update(),
                                    gr.update(),
                                ]
                                logger.info("手动停止定时抢票")
                                return
                        else:
                            break

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
                logger.info(f"1）订单准备")
                request_result_normal = _request.post(
                    url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                    data=token_payload,
                )
                request_result = request_result_normal.json()
                logger.info(f"请求头: {request_result_normal.headers} // 请求体: {request_result}")
                code = int(request_result["code"])
                # 完成验证码
                if code == -401:
                    # if True:
                    _url = "https://api.bilibili.com/x/gaia-vgate/v1/register"
                    _payload = urlencode(request_result["data"]["ga_data"]["riskParams"])
                    _data = _request.post(_url, _payload).json()
                    logger.info(
                        f"验证码请求: {_data}"
                    )
                    csrf = _request.cookieManager.get_cookies_value("bili_jct")
                    token = _data["data"]["token"]
                    if _data["data"]["type"] == "geetest":
                        gt = _data["data"]["geetest"]["gt"]
                        challenge = _data["data"]["geetest"]["challenge"]
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
                                gr.update(),
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
                                gr.update(value=withTimeString(f"等待验证码完成， 使用{ways[select_way]}"),
                                          visible=True),
                                gr.update(visible=True),
                                gr.update(),
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
                        _payload = {
                            "challenge": challenge,
                            "token": token,
                            "seccode": geetest_seccode,
                            "csrf": csrf,
                            "validate": geetest_validate,
                        }
                        _data = _request.post(_url, urlencode(_payload)).json()
                    elif _data["data"]["type"] == "phone":
                        _payload = {
                            "code": global_cookieManager.get_config_value("phone", ""),
                            "csrf": csrf,
                            "token": token,
                        }
                        _data = _request.post(_url, urlencode(_payload)).json()
                    else:
                        logger.warning("这个一个程序无法应对的验证码，脚本无法处理")
                        break
                    logger.info(f"validate: {_data}")
                    geetest_validate = ""
                    geetest_seccode = ""
                    if _data["code"] == 0:
                        logger.info("验证码成功")
                    else:
                        logger.info("验证码失败 {}", _data)
                        yield [
                            gr.update(value=withTimeString("验证码失败。重新验证"), visible=True),
                            gr.update(visible=True),
                            gr.update(),
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
                tickets_info["again"] = 1
                tickets_info["token"] = request_result["data"]["token"]
                logger.info(f"2）创建订单")
                tickets_info["timestamp"] = int(time.time()) * 100
                payload = format_dictionary_to_string(tickets_info)

                @retry.retry(exceptions=RequestException, tries=60, delay=interval / 1000)
                def inner_request():
                    nonlocal payload
                    if not isRunning:
                        raise ValueError("抢票结束")
                    ret = _request.post(
                        url=f"https://show.bilibili.com/api/ticket/order/createV2?project_id={tickets_info['project_id']}",
                        data=payload,
                    ).json()
                    err = int(ret["errno"])
                    logger.info(
                        f'状态码: {err}({ERRNO_DICT.get(err, "未知错误码")}), 请求体: {ret}'
                    )
                    if err == 100034:
                        logger.info(
                            f'更新票价为：{ret["data"]["pay_money"] / 100}'
                        )
                        tickets_info["pay_money"] = ret["data"]["pay_money"]
                        payload = format_dictionary_to_string(tickets_info)
                    if err == 0 or err == 100048 or err == 100079:
                        return ret, err
                    if err == 100051:
                        raise ValueError("token 过期")
                    if err != 0:
                        raise HTTPError("重试次数过多，重新准备订单")
                    return ret, err

                request_result, errno = inner_request()
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
                        gr.update(),
                    ]
                    pushplusToken = configDB.get("pushplusToken")
                    if pushplusToken is not None and pushplusToken != "":
                        PushPlusUtil.send_message(pushplusToken, "抢票成功", "前往订单中心付款吧")

                    serverchanKey = configDB.get("serverchanKey")
                    if serverchanKey is not None and serverchanKey != "":
                        ServerChanUtil.send_message(serverchanKey, "抢票成功", "前往订单中心付款吧")

                    if audio_path != "":
                        yield [
                            gr.update(value="开始放歌", visible=True),
                            gr.update(visible=False),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            gr.update(),
                            gr.update(value=audio_path, type="filepath", autoplay=True),
                        ]
                    break
                if mode == 1:
                    left_time -= 1
                    if left_time <= 0:
                        break
            except JSONDecodeError as e:
                logger.error(f"配置文件格式错误: {e}")
                return [
                    gr.update(value=withTimeString("配置文件格式错误"), visible=True),
                    gr.update(visible=True),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                ]
            except ValueError as e:
                logger.info(f"{e}")
                yield [
                    gr.update(value=withTimeString(f"有错误，具体查看控制台日志\n\n当前错误 {e}"), visible=True),
                    gr.update(visible=True),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),

                ]
            except HTTPError as e:
                logger.error(f"请求错误: {e}")
                yield [
                    gr.update(value=withTimeString(f"有错误，具体查看控制台日志\n\n当前错误 {e}"), visible=True),
                    gr.update(visible=True),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),

                ]
            except Exception as e:
                logger.exception(e)
                yield [
                    gr.update(value=withTimeString(f"有错误，具体查看控制台日志\n\n当前错误 {e}"), visible=True),
                    gr.update(visible=True),
                    gr.update(),
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
            gr.update(visible=False),  # 当设置play_sound_process,应该有提示声音
            gr.update(),
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
            return gr.update(value=withTimeString(f"验证码获取成功"), visible=True)
        else:
            return gr.update(value=withTimeString(f"验证码获取失败"), visible=True)

    gt_html_finish_btn.click(
        fn=None,
        inputs=None,
        outputs=geetest_result,
        js="() => captchaObj.getValidate()",
    )
    gt_html_finish_btn.click(fn=receive_geetest_result, inputs=geetest_result, outputs=go_ui)

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
        inputs=[ticket_ui, authcode_prepare_text_ui, authcode_preorder_time_ui, time_tmp, interval_ui, mode_ui,
                total_attempts_ui, api_key_input_ui, audio_path_ui],
        outputs=[go_ui, stop_btn, qr_image, gt_row, gt_ui, challenge_ui, trigger, audio_path_ui],
    )
    stop_btn.click(
        fn=stop,
        inputs=None,
        outputs=None,
    )
