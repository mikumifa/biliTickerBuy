import importlib
import json
import subprocess
import sys
import time
from datetime import datetime
from json import JSONDecodeError
from turtle import st
from urllib.parse import urlencode

import qrcode
from loguru import logger
from playsound3 import playsound
from requests import HTTPError, RequestException

from util import ERRNO_DICT, PushPlusUtil, ServerChanUtil
from util.BiliRequest import BiliRequest
from util import bili_ticket_gt_python

if bili_ticket_gt_python is not None:
    Amort = importlib.import_module("geetest.TripleValidator").TripleValidator()


def get_qrcode_url(_request, order_id) -> str:
    url = f"https://show.bilibili.com/api/ticket/order/getPayParam?order_id={order_id}"
    data = _request.get(url).json()
    if data["errno"] == 0:
        return data["data"]["code_url"]
    raise ValueError("获取二维码失败")


def buy_stream(
    tickets_info_str,
    time_start,
    interval,
    mode,
    total_attempts,
    timeoffset,
    audio_path,
    pushplusToken,
    serverchanKey,
    https_proxy: str = "none",
):
    if bili_ticket_gt_python is None:
        yield "当前设备不支持本地过验证码，无法使用"
        return

    isRunning = True
    left_time = total_attempts
    tickets_info = json.loads(tickets_info_str)
    cookies = tickets_info["cookies"]
    phone = tickets_info.get("phone", None)
    tickets_info.pop("cookies", None)
    tickets_info["buyer_info"] = json.dumps(tickets_info["buyer_info"])
    tickets_info["deliver_info"] = json.dumps(tickets_info["deliver_info"])
    _request = BiliRequest(cookies=cookies, proxy=https_proxy)

    token_payload = {
        "count": tickets_info["count"],
        "screen_id": tickets_info["screen_id"],
        "order_type": 1,
        "project_id": tickets_info["project_id"],
        "sku_id": tickets_info["sku_id"],
        "token": "",
        "newRisk": True,
    }

    if time_start != "":
        yield "0) 等待开始时间"
        yield f"时间偏差已被设置为: {timeoffset}s"
        try:
            time_difference = (
                datetime.strptime(time_start, "%Y-%m-%dT%H:%M:%S").timestamp()
                - time.time()
                + timeoffset
            )
        except ValueError:
            time_difference = (
                datetime.strptime(time_start, "%Y-%m-%dT%H:%M").timestamp()
                - time.time()
                + timeoffset
            )
        start_time = time.perf_counter()
        end_time = start_time + time_difference
        while time.perf_counter() < end_time:
            pass

    while isRunning:
        try:
            yield "1）订单准备"
            request_result_normal = _request.post(
                url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                data=token_payload,
                isJson=True,
            )
            request_result = request_result_normal.json()
            yield f"请求头: {request_result_normal.headers} // 请求体: {request_result}"
            code = int(request_result.get("errno", request_result.get("code")))

            if code == -401:
                _url = "https://api.bilibili.com/x/gaia-vgate/v1/register"
                _data = _request.post(
                    _url,
                    urlencode(request_result["data"]["ga_data"]["riskParams"]),
                ).json()
                yield f"验证码请求: {_data}"
                csrf: str = _request.cookieManager.get_cookies_value("bili_jct")  # type: ignore
                token: str = _data["data"]["token"]

                if _data["data"]["type"] == "geetest":
                    gt = _data["data"]["geetest"]["gt"]
                    challenge: str = _data["data"]["geetest"]["challenge"]
                    geetest_validate: str = Amort.validate(gt=gt, challenge=challenge)
                    geetest_seccode: str = geetest_validate + "|jordan"
                    yield f"geetest_validate: {geetest_validate},geetest_seccode: {geetest_seccode}"

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
                        "code": phone,
                        "csrf": csrf,
                        "token": token,
                    }
                    _data = _request.post(_url, urlencode(_payload)).json()
                else:
                    yield "这是一个程序无法应对的验证码，脚本无法处理"
                    break

                yield f"validate: {_data}"
                if int(_data.get("errno", _data.get("code"))) == 0:
                    yield "验证码成功"
                else:
                    yield f"验证码失败 {_data}"
                    continue

                request_result = _request.post(
                    url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                    data=token_payload,
                    isJson=True,
                ).json()
                yield f"prepare: {request_result}"

            tickets_info["again"] = 1
            tickets_info["token"] = request_result["data"]["token"]
            yield "2）创建订单"
            tickets_info["timestamp"] = int(time.time()) * 100
            payload = tickets_info
            result = None
            for attempt in range(1, 61):
                if not isRunning:
                    yield "抢票结束"
                    break
                try:
                    ret = _request.post(
                        url=f"https://show.bilibili.com/api/ticket/order/createV2?project_id={tickets_info['project_id']}",
                        data=payload,
                        isJson=True,
                    ).json()
                    err = int(ret.get("errno", ret.get("code")))
                    yield f"[尝试 {attempt}/60]  [{err}]({ERRNO_DICT.get(err, '未知错误码')}) | {ret}"

                    if err == 100034:
                        yield f"更新票价为：{ret['data']['pay_money'] / 100}"
                        tickets_info["pay_money"] = ret["data"]["pay_money"]
                        payload = tickets_info

                    if err in [0, 100048, 100079]:
                        yield "请求成功，停止重试"
                        result = (ret, err)
                        break

                    if err == 100051:
                        break

                    time.sleep(interval / 1000)

                except RequestException as e:
                    yield f"[尝试 {attempt}/60] 请求异常: {e}"
                    time.sleep(interval / 1000)

                except Exception as e:
                    yield f"[尝试 {attempt}/60] 未知异常: {e}"
                    time.sleep(interval / 1000)
            else:
                yield "重试次数过多，重新准备订单"
                continue
            if result is None:
                # if err == 100051:
                yield "token过期，需要重新准备订单"
                continue

            request_result, errno = result
            if errno == 0:
                yield "3）抢票成功，弹出付款二维码"
                qrcode_url = get_qrcode_url(
                    _request,
                    request_result["data"]["orderId"],
                )
                qr_gen = qrcode.QRCode()
                qr_gen.add_data(qrcode_url)
                qr_gen.make(fit=True)
                qr_gen_image = qr_gen.make_image()
                qr_gen_image.show()  # type: ignore
                if pushplusToken:
                    PushPlusUtil.send_message(
                        pushplusToken, "抢票成功", "前往订单中心付款吧"
                    )
                if serverchanKey:
                    ServerChanUtil.send_message(
                        serverchanKey, "抢票成功", "前往订单中心付款吧"
                    )
                if audio_path:
                    playsound(audio_path)
                break
            if mode == 1:
                left_time -= 1
                if left_time <= 0:
                    break
        except JSONDecodeError as e:
            yield f"配置文件格式错误: {e}"
        except HTTPError as e:
            logger.exception(e)
            yield f"请求错误: {e}"
        except Exception as e:
            logger.exception(e)
            yield f"程序异常: {repr(e)}"


def buy(
    tickets_info_str,
    time_start,
    interval,
    mode,
    total_attempts,
    timeoffset,
    audio_path,
    pushplusToken,
    serverchanKey,
):
    for msg in buy_stream(
        tickets_info_str,
        time_start,
        interval,
        mode,
        total_attempts,
        timeoffset,
        audio_path,
        pushplusToken,
        serverchanKey,
    ):
        logger.info(msg)


def buy_new_terminal(
    endpoint_url,
    filename,
    tickets_info_str,
    time_start,
    interval,
    mode,
    total_attempts,
    audio_path,
    pushplusToken,
    serverchanKey,
    timeoffset,
) -> subprocess.Popen:
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.extend(["main.py"])
    command.extend(
        [
            "buy",
            tickets_info_str,
            str(interval),
            str(mode),
            str(total_attempts),
            str(timeoffset),
        ]
    )
    if time_start:
        command.extend(["--time_start", time_start])
    if audio_path:
        command.extend(["--audio_path", audio_path])
    if pushplusToken:
        command.extend(["--pushplusToken", pushplusToken])
    if serverchanKey:
        command.extend(["--serverchanKey", serverchanKey])
    command.extend(["--filename", filename])
    command.extend(["--endpoint_url", endpoint_url])
    proc = subprocess.Popen(command)
    return proc
