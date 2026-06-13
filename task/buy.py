import json
import os
import subprocess
import sys
import time
import uuid
import copy
from random import randint
import datetime
from dataclasses import dataclass, field
from json import JSONDecodeError
import shutil
import qrcode
from loguru import logger

from requests import HTTPError, RequestException

from util import ERRNO_DICT, time_service
from util.Notifier import NotifierManager, NotifierConfig
from util.ProxyBackoff import ProxyBackoff
from util.BiliRequest import BiliRequest
from util.ProxyManager import ProxyManager
from util.RandomMessages import get_random_fail_message
from util.CTokenUtil import CTokenGenerator


base_url = "https://show.bilibili.com"
BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8), name="Asia/Shanghai")


@dataclass
class BuyStreamState:
    stage: str = "初始化"
    countdown: str = "-"
    current_proxy: str = "未初始化"
    proxy_pool: str = ""
    cooldown_remaining: int | None = None
    attempt_current: int | None = None
    attempt_total: int | None = None
    payment_qr_url: str | None = None
    status: str = "running"
    last_message: str = ""


@dataclass
class BuyStreamEvent:
    kind: str
    message: str | None
    state: BuyStreamState
    data: dict = field(default_factory=dict)


def get_qrcode_url(_request, order_id) -> str:
    url = f"{base_url}/api/ticket/order/getPayParam?order_id={order_id}"
    data = _request.get(url).json()
    if data.get("errno", data.get("code")) == 0:
        return data["data"]["code_url"]
    raise ValueError("获取二维码失败")


def _format_countdown(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}小时{minutes}分{secs}秒"


def _wait_until_start(time_start: str):
    if not time_start:
        return

    timeoffset = time_service.get_timeoffset()
    yield "0) 等待开始时间"
    yield f"时间偏差已被设置为: {timeoffset}秒"

    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
    ):
        try:
            target_time = datetime.datetime.strptime(time_start.strip(), fmt).replace(
                tzinfo=BEIJING_TZ
            )
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"无法解析抢票时间: {time_start!r}")

    yield f"计划抢票开始时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')}"

    time_difference = target_time.timestamp() - time.time() + timeoffset
    end_time = time.perf_counter() + time_difference
    next_report_at = float("inf")
    while True:
        remaining = end_time - time.perf_counter()
        if remaining <= 0:
            return
        if remaining <= next_report_at:
            yield f"距离开始抢票还有: {_format_countdown(remaining)}"
            next_report_at = max(0.0, remaining - 5)
        time.sleep(min(0.5, remaining))


def _build_token_payload(tickets_info: dict) -> dict:
    return {
        "count": tickets_info["count"],
        "screen_id": tickets_info["screen_id"],
        "order_type": 1,
        "project_id": tickets_info["project_id"],
        "sku_id": tickets_info["sku_id"],
        "token": "",
        "newRisk": True,
    }


def _build_order_payload(tickets_info: dict, token: str) -> dict:
    payload = dict(tickets_info)
    payload["again"] = 1
    payload["token"] = token
    payload["timestamp"] = int(time.time()) * 1000
    payload.pop("detail", None)
    return payload


def _is_create_success(ret: dict, err: int) -> bool:
    if err in {100048, 100079}:
        return True
    resp_message = str(ret.get("msg", ret.get("message", "")) or "")
    return err == 0 and "defaultBBR" not in resp_message


CREATE_RETRY_LIMIT = 60


def _format_retry_reason(
    err: int | None, ret: dict | None, exc: Exception | None
) -> str:
    if exc is not None:
        return f"最后一次异常: {exc}"
    if err is None:
        return "最后一次失败原因未知"
    reason = ERRNO_DICT.get(err, "未知错误码")
    detail = ret if ret is not None else {}
    return f"最后一次返回: [{err}]({reason}) | {detail}"


def _summarize_non_json_response(prefix: str, diagnostic: str) -> str:
    if "status=412" in diagnostic:
        return f"{prefix}触发 412 风控"

    content_type = "未知"
    for part in diagnostic.split(", "):
        if part.startswith("content_type="):
            content_type = part.split("=", 1)[1]
            break
    return f"{prefix}返回了非 JSON 响应（{content_type}）"


def _format_attempt_result(attempt: int, err: int, ret: dict) -> str:
    prefix = f"[{attempt}/{CREATE_RETRY_LIMIT}]"
    reason = ERRNO_DICT.get(err)
    if reason:
        return f"{prefix} [{err}] {reason}"
    return f"{prefix} [{err}] 未知错误码 | {ret}"


def _build_proxy_exhausted_message(_request: BiliRequest, delay_seconds: int) -> str:
    return (
        "当前所有代理暂时不可用，请尽快补充或更换代理。"
        f"程序将休息 {delay_seconds} 秒后继续尝试。"
        f" 代理池状态：{_request.proxy_pool_status()}"
    )


def _notify_proxy_exhausted(
    notifier_config: NotifierConfig,
    _request: BiliRequest,
    delay_seconds: int,
) -> None:
    if not notifier_config.notify_proxy_exhausted:
        return

    manager = NotifierManager.create_from_config(
        config=notifier_config,
        title="代理已全部失效",
        content=_build_proxy_exhausted_message(_request, delay_seconds),
        include_audio=False,
    )
    manager.start_all()


def _handle_proxy_failure(
    _request: BiliRequest,
    reason: str,
    proxy_backoff: ProxyBackoff,
    notifier_config: NotifierConfig,
) -> tuple[list[str], int | None]:
    messages: list[str] = []
    previous_proxy = _request.current_proxy_display()
    cooled = _request.mark_current_proxy_failure(reason)
    if cooled:
        messages.append(f"代理冷却: {previous_proxy} 短时间内连续失败，已暂时停用")

    if _request.switch_proxy():
        proxy_backoff.reset()
        messages.append(f"切换代理到 {_request.current_proxy_display()}")
        return messages, None

    if _request.has_available_proxy():
        return messages, None

    delay_seconds = proxy_backoff.next_delay_seconds()
    if proxy_backoff.should_notify():
        _notify_proxy_exhausted(notifier_config, _request, delay_seconds)
    messages.append(f"所有代理当前不可用，休息 {delay_seconds} 秒后再试")
    return messages, delay_seconds


def _format_status_result(prefix: str, ret: dict) -> str:
    err = int(ret.get("errno", ret.get("code", -1)))
    reason = ERRNO_DICT.get(err)
    if reason:
        return f"{prefix}: [{err}] {reason}"
    message = str(ret.get("msg", ret.get("message", "")) or "")
    if message:
        return f"{prefix}: [{err}] {message}"
    return f"{prefix}: [{err}] {ret}"


def buy_stream(
    tickets_info,
    time_start,
    interval,
    notifier_config,
    https_proxys,
    show_random_message=True,
    show_qrcode=True,
    readable=False,
):
    state = BuyStreamState()

    def emit(kind: str, message: str | None, **data):
        if "stage" in data:
            state.stage = data["stage"]
        if "countdown" in data:
            state.countdown = data["countdown"]
        if "current_proxy" in data:
            state.current_proxy = data["current_proxy"]
        if "proxy_pool" in data:
            state.proxy_pool = data["proxy_pool"]
        if "cooldown_remaining" in data:
            state.cooldown_remaining = data["cooldown_remaining"]
        if "attempt_current" in data:
            state.attempt_current = data["attempt_current"]
        if "attempt_total" in data:
            state.attempt_total = data["attempt_total"]
        if "payment_qr_url" in data:
            state.payment_qr_url = data["payment_qr_url"]
        if "status" in data:
            state.status = data["status"]
        if message is not None:
            state.last_message = message

        if readable:
            return BuyStreamEvent(
                kind=kind,
                message=message,
                state=copy.deepcopy(state),
                data=data,
            )
        return message

    def emit_proxy_failure_messages(
        reason: str,
        *,
        attempt: int | None = None,
    ):
        messages, delay_seconds = _handle_proxy_failure(
            _request,
            reason,
            proxy_backoff,
            notifier_config,
        )
        for message in messages:
            yield emit(
                "proxy",
                message,
                current_proxy=_request.current_proxy_status(),
                proxy_pool=_request.proxy_pool_status(),
                cooldown_remaining=None,
                status="running",
                attempt_current=attempt,
                attempt_total=(
                    CREATE_RETRY_LIMIT if attempt is not None else state.attempt_total
                ),
            )
        if delay_seconds is not None:
            for remaining in range(delay_seconds, 0, -1):
                yield emit(
                    "state",
                    None,
                    status="cooldown",
                    cooldown_remaining=remaining,
                    current_proxy=_request.current_proxy_status(),
                    proxy_pool=_request.proxy_pool_status(),
                    attempt_current=attempt,
                    attempt_total=(
                        CREATE_RETRY_LIMIT
                        if attempt is not None
                        else state.attempt_total
                    ),
                )
                time.sleep(1)
            if _request.ensure_active_proxy():
                proxy_backoff.reset()
                yield emit(
                    "state",
                    None,
                    current_proxy=_request.current_proxy_status(),
                    proxy_pool=_request.proxy_pool_status(),
                    cooldown_remaining=None,
                    status="running",
                    attempt_current=attempt,
                    attempt_total=(
                        CREATE_RETRY_LIMIT
                        if attempt is not None
                        else state.attempt_total
                    ),
                )

    isRunning = True
    tickets_info = json.loads(tickets_info)
    detail = tickets_info["detail"]
    cookies = tickets_info["cookies"]
    tickets_info.pop("cookies", None)
    tickets_info["buyer_info"] = json.dumps(tickets_info["buyer_info"])
    tickets_info["deliver_info"] = json.dumps(tickets_info["deliver_info"])
    masked_proxies = ProxyManager.mask_proxy_string(https_proxys)
    logger.info(f"使用代理：{masked_proxies or '直连'}")
    _request = BiliRequest(cookies=cookies, proxy=https_proxys)
    proxy_backoff = ProxyBackoff()

    is_hot_project = bool(tickets_info.get("is_hot_project", False))
    token_payload = _build_token_payload(tickets_info)

    for wait_message in _wait_until_start(time_start):
        countdown_value = None
        stage_value = None
        if wait_message.startswith("0)"):
            stage_value = "等待开票"
        elif wait_message.startswith("距离开始抢票还有:"):
            countdown_value = wait_message.split(":", 1)[1].strip()
        yield emit(
            "status",
            wait_message,
            stage=stage_value or state.stage,
            countdown=countdown_value or state.countdown,
        )
    yield emit(
        "proxy",
        f"当前代理: {_request.current_proxy_status()}",
        current_proxy=_request.current_proxy_status(),
        proxy_pool=_request.proxy_pool_status(),
    )

    while isRunning:
        try:
            yield emit("stage", "1）订单准备", stage="订单准备")
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
            try:
                request_result = request_result_normal.json()
            except JSONDecodeError:
                diagnostic = _request.describe_non_json_response(request_result_normal)
                summary = _summarize_non_json_response("订单准备接口", diagnostic)
                if "412 风控" in summary:
                    summary += f"（当前代理: {_request.current_proxy_display()}）"
                    for message in emit_proxy_failure_messages("订单准备接口 412 风控"):
                        yield message
                yield emit(
                    "error",
                    summary,
                    current_proxy=_request.current_proxy_status(),
                    proxy_pool=_request.proxy_pool_status(),
                )
                continue
            proxy_backoff.reset()
            yield emit("status", _format_status_result("订单准备结果", request_result))
            yield emit(
                "stage",
                "2）创建订单",
                stage="创建订单",
                attempt_current=None,
                attempt_total=CREATE_RETRY_LIMIT,
            )
            payload = _build_order_payload(
                tickets_info, request_result["data"]["token"]
            )

            result = None
            last_err: int | None = None
            last_ret: dict | None = None
            last_exc: Exception | None = None
            for attempt in range(1, CREATE_RETRY_LIMIT + 1):
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
                    create_response = _request.post(
                        url=url,
                        data=payload,
                        isJson=True,
                    )
                    try:
                        ret = create_response.json()
                    except JSONDecodeError as exc:
                        diagnostic = _request.describe_non_json_response(
                            create_response
                        )
                        summary = _summarize_non_json_response(
                            "创建订单接口", diagnostic
                        )
                        if "412 风控" in summary:
                            summary += (
                                f"（当前代理: {_request.current_proxy_display()}）"
                            )
                            for message in emit_proxy_failure_messages(
                                "创建订单接口 412 风控",
                                attempt=attempt,
                            ):
                                yield message
                        raise RuntimeError(summary) from exc
                    proxy_backoff.reset()
                    err = int(ret.get("errno", ret.get("code")))
                    last_err = err
                    last_ret = ret
                    last_exc = None
                    if err == 100034:
                        yield emit(
                            "status",
                            f"更新票价为：{ret['data']['pay_money'] / 100}",
                            attempt_current=attempt,
                            attempt_total=CREATE_RETRY_LIMIT,
                        )
                        payload["pay_money"] = ret["data"]["pay_money"]
                    if _is_create_success(ret, err):
                        yield emit(
                            "success",
                            "请求成功，停止重试",
                            attempt_current=attempt,
                            attempt_total=CREATE_RETRY_LIMIT,
                        )
                        result = (ret, err)
                        break
                    if err == 100051:
                        break
                    yield emit(
                        "attempt",
                        _format_attempt_result(attempt, err, ret),
                        attempt_current=attempt,
                        attempt_total=CREATE_RETRY_LIMIT,
                    )

                    time.sleep(interval / 1000)

                except RequestException as e:
                    last_exc = e
                    for message in emit_proxy_failure_messages(
                        f"创建订单请求异常({e.__class__.__name__})",
                        attempt=attempt,
                    ):
                        yield message
                    yield emit(
                        "attempt",
                        f"[{attempt}/{CREATE_RETRY_LIMIT}] {e}",
                        attempt_current=attempt,
                        attempt_total=CREATE_RETRY_LIMIT,
                    )
                    time.sleep(interval / 1000)

                except RuntimeError as e:
                    last_exc = e
                    yield emit(
                        "attempt",
                        f"[{attempt}/{CREATE_RETRY_LIMIT}] {e}",
                        attempt_current=attempt,
                        attempt_total=CREATE_RETRY_LIMIT,
                    )
                    time.sleep(interval / 1000)

                except Exception as e:
                    last_exc = e
                    yield emit(
                        "attempt",
                        f"[{attempt}/{CREATE_RETRY_LIMIT}] {e}",
                        attempt_current=attempt,
                        attempt_total=CREATE_RETRY_LIMIT,
                    )
                    time.sleep(interval / 1000)
            else:
                if show_random_message:
                    yield emit("status", f"群友说👴： {get_random_fail_message()}")
                yield emit(
                    "status",
                    f"创建订单已重试 {CREATE_RETRY_LIMIT} 次，重新准备订单",
                    attempt_current=None,
                    attempt_total=CREATE_RETRY_LIMIT,
                )
                continue
            if result is None:
                if last_err == 100051:
                    yield emit("status", "token过期，需要重新准备订单")
                else:
                    yield emit(
                        "status",
                        "本轮创建订单未成功，"
                        f"{_format_retry_reason(last_err, last_ret, last_exc)}，重新准备订单",
                    )
                continue

            request_result, errno = result
            if errno == 0:
                notifierManager = NotifierManager.create_from_config(
                    config=notifier_config,
                    title="抢票成功",
                    content=f"bilibili会员购，请尽快前往订单中心付款: {detail}",
                )

                notifierManager.start_all()

                yield emit(
                    "stage",
                    "3）抢票成功，弹出付款二维码",
                    stage="抢票成功",
                    status="succeeded",
                )
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
                    yield emit(
                        "payment_qr",
                        "PAYMENT_QR_URL={0}".format(qrcode_url),
                        payment_qr_url=qrcode_url,
                        status="succeeded",
                    )
                break
            if errno == 100079:
                yield emit("status", "有重复订单，停止重试", status="completed")
                break
        except JSONDecodeError as e:
            yield emit("error", f"配置文件格式错误: {e}", status="failed")
        except HTTPError as e:
            logger.exception(e)
            yield emit("error", f"请求错误: {e}")
            for message in emit_proxy_failure_messages(
                f"订单准备请求异常({e.__class__.__name__})"
            ):
                yield message
        except RequestException as e:
            logger.exception(e)
            yield emit("error", f"请求错误: {e}")
            for message in emit_proxy_failure_messages(
                f"订单准备请求异常({e.__class__.__name__})"
            ):
                yield message
        except Exception as e:
            logger.exception(e)
            yield emit("error", f"程序异常: {repr(e)}", status="failed")


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
    meowNickname=None,
    notify_proxy_exhausted=False,
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
        meow_nickname=meowNickname,
        audio_path=audio_path,
        notify_proxy_exhausted=notify_proxy_exhausted,
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
        if msg is not None:
            logger.info(msg)


def buy_new_terminal(
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
    meowNickname=None,
    notify_proxy_exhausted=False,
    show_random_message=True,
    log_file_path: str | None = None,
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
    if meowNickname:
        command.extend(["--meowNickname", meowNickname])
    if notify_proxy_exhausted:
        command.append("--notify_proxy_exhausted")
    if https_proxys:
        command.extend(["--https_proxys", https_proxys])
    if not show_random_message:
        command.extend(["--hide_random_message"])
    env = os.environ.copy()
    if log_file_path:
        env["BTB_APP_LOG_NAME"] = os.path.basename(log_file_path)
    else:
        env.setdefault("BTB_APP_LOG_NAME", f"{uuid.uuid4()}.log")
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE
        )
        env["BTB_HOLD_TERMINAL"] = "1"
    else:
        env["BTB_CHILD_PROCESS"] = "1"
        kwargs["start_new_session"] = True

    if os.name == "nt":
        proc = subprocess.Popen(
            command,
            env=env,
            **kwargs,
        )
        return proc

    with open(os.devnull, "r") as devnull_in, open(os.devnull, "a") as devnull_out:
        proc = subprocess.Popen(
            command,
            env=env,
            stdin=devnull_in,
            stdout=devnull_out,
            stderr=devnull_out,
            **kwargs,
        )
    return proc
