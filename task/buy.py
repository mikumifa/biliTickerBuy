import json
import os
import subprocess
import sys
import time
from random import randint
from datetime import datetime
from json import JSONDecodeError
import shutil
import qrcode
from loguru import logger

from requests import HTTPError, RequestException

from util import ERRNO_DICT, time_service
from util.Notifier import NotifierManager, NotifierConfig
from util.BiliRequest import BiliRequest
from util.RandomMessages import get_random_fail_message
from util.CTokenUtil import CTokenGenerator


base_url = "https://show.bilibili.com"


def get_qrcode_url(_request, order_id) -> str:
    url = f"{base_url}/api/ticket/order/getPayParam?order_id={order_id}"
    data = _request.get(url).json()
    if data.get("errno", data.get("code")) == 0:
        return data["data"]["code_url"]
    raise ValueError("获取二维码失败")


def buy_stream(
    tickets_info,
    time_start,
    interval,
    notifier_config,
    https_proxys,
    show_random_message=True,
    show_qrcode=True,
):
    isRunning = True
    tickets_info = json.loads(tickets_info)
    detail = tickets_info["detail"]
    cookies = tickets_info["cookies"]
    phone = tickets_info.get("phone", None)
    tickets_info.pop("cookies", None)
    tickets_info["buyer_info"] = json.dumps(tickets_info["buyer_info"])
    tickets_info["deliver_info"] = json.dumps(tickets_info["deliver_info"])
    logger.info(f"使用代理：{https_proxys}")
    _request = BiliRequest(cookies=cookies, proxy=https_proxys)

    if "is_hot_project" in tickets_info:
        is_hot_project = tickets_info["is_hot_project"]
    else:
        is_hot_project = False

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
        timeoffset = time_service.get_timeoffset()
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
        while True:
            now = time.perf_counter()
            if now >= end_time:
                break
            remaining = end_time - now
            time.sleep(min(0.5, remaining))

    while isRunning:
        try:
            yield "1）订单准备"
            if is_hot_project:
                ctoken_generator = CTokenGenerator(time.time(), 0, randint(2000, 10000))
                token_payload["token"] = ctoken_generator.generate_ctoken(
                    is_create_v2=False
                )
            request_result_normal = _request.post(
                url=f"{base_url}/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                data=token_payload,
                isJson=True,
            )
            request_result = request_result_normal.json()
            yield f"请求头: {request_result_normal.headers} // 请求体: {request_result}"
            tickets_info["again"] = 1
            tickets_info["token"] = request_result["data"]["token"]
            yield "2）创建订单"
            tickets_info["timestamp"] = int(time.time()) * 1000
            payload = tickets_info
            if "detail" in payload:
                del payload["detail"]

            result = None
            for attempt in range(1, 61):
                if not isRunning:
                    yield "抢票结束"
                    break
                try:
                    url = f"{base_url}/api/ticket/order/createV2?project_id={tickets_info['project_id']}"
                    if is_hot_project:
                        payload["ctoken"] = ctoken_generator.generate_ctoken(  # type: ignore
                            is_create_v2=True
                        )
                        ptoken = request_result["data"]["ptoken"] or ""
                        payload["ptoken"] = ptoken
                        payload["orderCreateUrl"] = (
                            "https://show.bilibili.com/api/ticket/order/createV2"
                        )
                        url += "&ptoken=" + ptoken
                    ret = _request.post(
                        url=url,
                        data=payload,
                        isJson=True,
                    ).json()
                    err = int(ret.get("errno", ret.get("code")))
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
                    yield f"[尝试 {attempt}/60]  [{err}]({ERRNO_DICT.get(err, '未知错误码')}) | {ret}"

                    time.sleep(interval / 1000)

                except RequestException as e:
                    yield f"[尝试 {attempt}/60] 请求异常: {e}"
                    time.sleep(interval / 1000)

                except Exception as e:
                    yield f"[尝试 {attempt}/60] 未知异常: {e}"
                    time.sleep(interval / 1000)
            else:
                if show_random_message:
                    yield f"群友说👴： {get_random_fail_message()}"
                yield "重试次数过多，重新准备订单"
                continue
            if result is None:
                yield "token过期，需要重新准备订单"
                continue

            request_result, errno = result
            if errno == 0:
                # 使用统一的工厂方法创建NotifierManager
                # 不传递interval_seconds和duration_minutes，让每个推送渠道使用自己的默认值
                notifierManager = NotifierManager.create_from_config(
                    config=notifier_config,
                    title="抢票成功",
                    content=f"bilibili会员购，请尽快前往订单中心付款: {detail}",
                )

                # 启动所有已配置的推送渠道
                notifierManager.start_all()

                yield "3）抢票成功，弹出付款二维码"
                qrcode_url = get_qrcode_url(
                    _request,
                    request_result["data"]["orderId"],
                )
                if show_qrcode:
                    qr_gen = qrcode.QRCode()
                    qr_gen.add_data(qrcode_url)
                    qr_gen.make(fit=True)
                    qr_gen_image = qr_gen.make_image()
                    qr_gen_image.show()  # type: ignore
                else:
                    yield "PAYMENT_QR_URL={0}".format(qrcode_url)
                break
            if errno == 100079:
                yield "有重复订单，停止重试"
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
    tickets_info,
    time_start,
    interval,
    audio_path,
    pushplusToken,
    serverchanKey,
    barkToken,
    https_proxys,
    serverchan3ApiUrl=None,
    ntfy_url=None,
    ntfy_username=None,
    ntfy_password=None,
    show_random_message=True,
    show_qrcode=True,
):
    # 创建NotifierConfig对象
    notifier_config = NotifierConfig(
        serverchan_key=serverchanKey,
        serverchan3_api_url=serverchan3ApiUrl,
        pushplus_token=pushplusToken,
        bark_token=barkToken,
        ntfy_url=ntfy_url,
        ntfy_username=ntfy_username,
        ntfy_password=ntfy_password,
        audio_path=audio_path,
    )

    for msg in buy_stream(
        tickets_info,
        time_start,
        interval,
        notifier_config,
        https_proxys,
        show_random_message,
        show_qrcode,
    ):
        logger.info(msg)


def buy_new_terminal(
    endpoint_url,
    tickets_info,
    time_start,
    interval,
    audio_path,
    pushplusToken,
    serverchanKey,
    barkToken,
    https_proxys,
    serverchan3ApiUrl=None,
    ntfy_url=None,
    ntfy_username=None,
    ntfy_password=None,
    show_random_message=True,
    terminal_ui="网页",
) -> subprocess.Popen:
    command = None

    # 1️⃣ PyInstaller / frozen
    if getattr(sys, "frozen", False):
        command = [sys.executable]
    else:
        # 2️⃣ 源码模式：检查「当前脚本目录」是否有 main.py
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        main_py = os.path.join(script_dir, "main.py")

        if os.path.exists(main_py):
            command = [sys.executable, main_py]
        # 3️⃣ 兜底：使用 btb（pip / pipx）
        else:
            btb_path = shutil.which("btb")
            if not btb_path:
                raise RuntimeError("Cannot find main.py or btb command")

            command = [btb_path]
    command.extend(["buy", tickets_info])
    if interval is not None:
        command.extend(["--interval", str(interval)])
    if time_start:
        command.extend(["--time_start", time_start])
    if audio_path:
        command.extend(["--audio_path", audio_path])
    if pushplusToken:
        command.extend(["--pushplusToken", pushplusToken])
    if serverchanKey:
        command.extend(["--serverchanKey", serverchanKey])
    if serverchan3ApiUrl:
        command.extend(["--serverchan3ApiUrl", serverchan3ApiUrl])
    if barkToken:
        command.extend(["--barkToken", barkToken])
    if ntfy_url:
        command.extend(["--ntfy_url", ntfy_url])
    if ntfy_username:
        command.extend(["--ntfy_username", ntfy_username])
    if ntfy_password:
        command.extend(["--ntfy_password", ntfy_password])
    if https_proxys:
        command.extend(["--https_proxys", https_proxys])
    if not show_random_message:
        command.extend(["--hide_random_message"])
    if terminal_ui == "网页":
        command.append("--web")
    command.extend(["--endpoint_url", endpoint_url])
    if terminal_ui == "网页":
        proc = subprocess.Popen(command)
    else:
        proc = subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
    return proc
