import importlib
import json
import subprocess
import sys
import time
from datetime import datetime
from json import JSONDecodeError
from urllib.parse import urlencode
from playsound3 import playsound
import qrcode
import retry
from loguru import logger
from requests import HTTPError, RequestException
from util import PushPlusUtil, ServerChanUtil
from util.BiliRequest import BiliRequest, format_dictionary_to_string
from util.dynimport import bili_ticket_gt_python
from util.error import ERRNO_DICT
from util.order_qrcode import get_qrcode_url

if bili_ticket_gt_python is not None:
    Amort = importlib.import_module("geetest.AmorterValidator").AmorterValidator()


@logger.catch
def buy(tickets_info_str, time_start, interval, mode, total_attempts, timeoffset, audio_path, pushplusToken,
        serverchanKey, phone):
    if bili_ticket_gt_python is None:
        logger.info("当前设备不支持本地过验证码，无法多开")
        return
    isRunning = True
    left_time = total_attempts
    tickets_info = json.loads(tickets_info_str)
    cookies = tickets_info["cookies"]
    del tickets_info["cookies"]
    _request = BiliRequest(cookies=cookies)
    token_payload = {"count": tickets_info["count"], "screen_id": tickets_info["screen_id"], "order_type": 1,
                     "project_id": tickets_info["project_id"], "sku_id": tickets_info["sku_id"], "token": "",
                     "newRisk": True, }
    if time_start != "":
        logger.info("0) 等待开始时间")
        logger.info("时间偏差已被设置为: " + str(timeoffset) + 's')
        try:
            time_difference = (
                    datetime.strptime(time_start, "%Y-%m-%dT%H:%M:%S").timestamp() - time.time() + timeoffset)
        except ValueError as e:
            time_difference = (
                    datetime.strptime(time_start, "%Y-%m-%dT%H:%M").timestamp() - time.time() + timeoffset)
        start_time = time.perf_counter()
        end_time = start_time + time_difference
        current_time = start_time
        while current_time < end_time:
            current_time = time.perf_counter()
    while isRunning:
        try:
            # 订单准备
            logger.info(f"1）订单准备")
            request_result_normal = _request.post(
                url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                data=token_payload, )
            request_result = request_result_normal.json()
            logger.info(f"请求头: {request_result_normal.headers} // 请求体: {request_result}")
            code = int(request_result["code"])
            # 完成验证码
            if code == -401:
                # if True:
                _url = "https://api.bilibili.com/x/gaia-vgate/v1/register"
                _payload = urlencode(request_result["data"]["ga_data"]["riskParams"])
                _data = _request.post(_url, _payload).json()
                logger.info(f"验证码请求: {_data}")
                csrf = _request.cookieManager.get_cookies_value("bili_jct")
                token = _data["data"]["token"]
                if _data["data"]["type"] == "geetest":
                    gt = _data["data"]["geetest"]["gt"]
                    challenge = _data["data"]["geetest"]["challenge"]
                    geetest_validate = Amort.validate(gt=gt, challenge=challenge)
                    geetest_seccode = geetest_validate + "|jordan"
                    logger.info(f"geetest_validate: {geetest_validate},geetest_seccode: {geetest_seccode}")
                    _url = "https://api.bilibili.com/x/gaia-vgate/v1/validate"
                    _payload = {"challenge": challenge, "token": token, "seccode": geetest_seccode, "csrf": csrf,
                                "validate": geetest_validate, }
                    _data = _request.post(_url, urlencode(_payload)).json()
                elif _data["data"]["type"] == "phone":
                    _payload = {"code": phone, "csrf": csrf, "token": token, }
                    _data = _request.post(_url, urlencode(_payload)).json()
                else:
                    logger.warning("这个一个程序无法应对的验证码，脚本无法处理")
                    break
                logger.info(f"validate: {_data}")
                if _data["code"] == 0:
                    logger.info("验证码成功")
                else:
                    logger.info("验证码失败 {}", _data)
                    continue
                request_result = _request.post(
                    url=f"https://show.bilibili.com/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                    data=token_payload, ).json()
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
                    data=payload, ).json()
                err = int(ret["errno"])
                logger.info(f'状态码: {err}({ERRNO_DICT.get(err, "未知错误码")}), 响应: {ret}')
                if err == 100034:
                    logger.info(f'更新票价为：{ret["data"]["pay_money"] / 100}')
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
                f'状态码: {errno}({ERRNO_DICT.get(errno, "未知错误码")}), 响应: {request_result} 剩余次数: {left_time_str}')
            if errno == 0:
                logger.info(f"3）抢票成功")
                qrcode_url = get_qrcode_url(_request, request_result["data"]["orderId"], )
                qr_gen = qrcode.QRCode()
                qr_gen.add_data(qrcode_url)
                qr_gen.make(fit=True)
                qr_gen_image = qr_gen.make_image()
                qr_gen_image.show()
                if pushplusToken is not None and pushplusToken != "":
                    PushPlusUtil.send_message(pushplusToken, "抢票成功", "前往订单中心付款吧")
                if serverchanKey is not None and serverchanKey != "":
                    ServerChanUtil.send_message(serverchanKey, "抢票成功", "前往订单中心付款吧")
                if audio_path != "":
                    playsound(audio_path)
                break
            if mode == 1:
                left_time -= 1
                if left_time <= 0:
                    break
        except JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
        except ValueError as e:
            logger.info(f"{e}")
        except HTTPError as e:
            logger.error(f"请求错误: {e}")
        except Exception as e:
            logger.exception(e)
        finally:
            while True:
                time.sleep(1)


def buy_new_terminal(tickets_info_str, time_start, interval, mode, total_attempts, audio_path, pushplusToken,
                     serverchanKey, timeoffset, phone):
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.extend(["main.py"])
    command.extend([
        "buy",
        tickets_info_str, str(interval), str(mode), str(total_attempts),
        str(timeoffset),
    ])
    logger.info(command)
    if time_start:
        command.extend(["--time_start", time_start])
    if audio_path:
        command.extend(["--audio_path", audio_path])
    if pushplusToken:
        command.extend(["--pushplusToken", pushplusToken])
    if serverchanKey:
        command.extend(["--serverchanKey", serverchanKey])
    if phone:
        command.extend(["--phone", phone])

    if sys.platform == "win32":
        subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif sys.platform == "linux":
        logger.warning("当前系统未实现终端启动功能")
    else:
        logger.warning("当前系统未实现终端启动功能")
