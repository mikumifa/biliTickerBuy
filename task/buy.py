import json
import os
import subprocess
import sys
import time
import uuid
import copy
from random import randint
import datetime
from collections.abc import Generator
from dataclasses import dataclass, field
from json import JSONDecodeError
import shutil
import qrcode
from loguru import logger

from requests import HTTPError, RequestException
from util.CTokenUtil import (
    CTokenRuntimeState,
    generate_browser_window_state,
    init_ctoken_state,
)

from util import time_service
from util.Notifier import NotifierManager, NotifierConfig
from util.ProxyBackoff import ProxyBackoff
from util.BiliRequest import BiliRequest
from util.ProxyManager import ProxyManager
from util.RandomMessages import get_random_fail_message
from util.TimeUtil import current_time_ms
from util.TokenUtil import generate_token
from util.error_codes import ErrorCodes


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


@dataclass
class RetryOutcome:
    err: int | None = None
    ret: dict | None = None
    exc: Exception | None = None

    def set_response(self, err: int, ret: dict) -> None:
        self.err = err
        self.ret = ret
        self.exc = None

    def set_exception(self, exc: Exception) -> None:
        self.exc = exc


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
    count = int(tickets_info["count"])
    screen_id = int(tickets_info["screen_id"])
    order_type = int(tickets_info.get("order_type", 1))
    project_id = int(tickets_info["project_id"])
    sku_id = int(tickets_info["sku_id"])
    return {
        "count": count,
        "screen_id": screen_id,
        "order_type": order_type,
        "project_id": project_id,
        "sku_id": sku_id,
        "buyer_info": tickets_info.get(
            "_prepare_buyer_info",
            tickets_info.get("buyer_info", []),
        ),
        "ignoreRequestLimit": True,
        "ticket_agent": "",
        "token": "",
        "newRisk": True,
        "requestSource": "neul-next",
    }


def _build_order_token(tickets_info: dict) -> str:
    return generate_token(
        project_id=int(tickets_info["project_id"]),
        screen_id=int(tickets_info["screen_id"]),
        order_type=int(tickets_info.get("order_type", 1)),
        count=int(tickets_info["count"]),
        sku_id=int(tickets_info["sku_id"]),
    )


def _normalize_prepare_ptoken(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).replace("=", "")


def _build_click_position(origin_ms: int, now_ms: int) -> dict[str, int]:
    return {
        "x": randint(400, 900),
        "y": randint(400, 900),
        "origin": origin_ms - randint(0, 1000),
        "now": now_ms,
    }


def _is_create_success(ret: dict, err: int) -> bool:
    if err in {100048, 100079}:
        return True
    resp_message = str(ret.get("msg", ret.get("message", "")) or "")
    return err == 0 and "defaultBBR" not in resp_message


CREATE_RETRY_LIMIT = 60
CREATE_REQUEST_BATCH_SIZE = 30


def _extract_response_message(ret: dict) -> str:
    return str(ret.get("msg", ret.get("message", "")) or "").strip()


def _append_response_message(err: int, base: str, ret: dict | None) -> str:
    return ErrorCodes.append_response_message(err, base, ret)


def _format_retry_reason(outcome: RetryOutcome) -> str:
    if outcome.exc is not None:
        return f"最后一次异常: {outcome.exc}"
    if outcome.err is None:
        return "最后一次失败原因未知"
    reason = ErrorCodes.get_message_or_unknown(outcome.err)
    detail = outcome.ret if outcome.ret is not None else {}
    base = f"最后一次返回: [{outcome.err}]({reason}) | {detail}"
    return _append_response_message(outcome.err, base, outcome.ret)


def _summarize_non_json_response(prefix: str, diagnostic: str) -> str:
    if "status=412" in diagnostic:
        return f"{prefix}触发 412 风控"

    content_type = "未知"
    for part in diagnostic.split(", "):
        if part.startswith("content_type="):
            content_type = part.split("=", 1)[1]
            break
    return f"{prefix}返回了非 JSON 响应（{content_type}）"


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
) -> tuple[str | None, int | None]:
    """Handle a proxy failure and return the immediate status plus cooldown plan."""
    previous_proxy = _request.current_proxy_display()
    cooled = _request.mark_current_proxy_failure(reason)
    if cooled:
        immediate_message = f"代理冷却: {previous_proxy} 短时间内连续失败，已暂时停用"
    else:
        immediate_message = None

    if _request.switch_proxy():
        proxy_backoff.reset()
        switched_message = f"切换代理到 {_request.current_proxy_display()}"
        if immediate_message:
            return f"{immediate_message}\n{switched_message}", None
        return switched_message, None

    if _request.has_available_proxy():
        return immediate_message, None

    delay_seconds = proxy_backoff.next_delay_seconds()
    if proxy_backoff.should_notify():
        _notify_proxy_exhausted(notifier_config, _request, delay_seconds)
    exhausted_message = f"所有代理当前不可用，休息 {delay_seconds} 秒后再试"
    if immediate_message:
        return f"{immediate_message}\n{exhausted_message}", delay_seconds
    return exhausted_message, delay_seconds


def _format_status_result(prefix: str, ret: dict) -> str:
    err = int(ret.get("errno", ret.get("code", -1)))
    reason = ErrorCodes.get_message(err)
    if reason:
        return _append_response_message(err, f"{prefix}: [{err}] {reason}", ret)
    message = _extract_response_message(ret)
    if message:
        return f"{prefix}: [{err}] {message}"
    return f"{prefix}: [{err}] {ret}"


def _prepare_create_request(
    request: BiliRequest,
    ticket_collection: CTokenRuntimeState,
    tickets_info: dict,
    order_token: str,
    timeoffset: float,
    is_hot_project: bool,
    request_result: dict | None,
) -> tuple[str, dict, dict[str, int] | None]:
    payload = dict(tickets_info)
    payload["again"] = 1
    payload["token"] = order_token
    payload["timestamp"] = current_time_ms(timeoffset=timeoffset)
    payload["newRisk"] = True
    payload["requestSource"] = "neul-next"
    payload.pop("detail", None)
    payload.pop("sale_start", None)
    payload.pop("username", None)
    payload.pop("_prepare_buyer_info", None)
    url = (
        f"{base_url}/api/ticket/order/createV2?project_id={tickets_info['project_id']}"
    )

    if not is_hot_project:
        return url, payload

    payload["clickPosition"] = _build_click_position(
        request.createTime, current_time_ms(timeoffset=timeoffset)
    )
    snapshot = ticket_collection.snapshot()
    payload["ctoken"] = snapshot.generate_ctoken()
    logger.info(snapshot)
    logger.info(f"ctoken: {payload['ctoken']}")
    ptoken = _normalize_prepare_ptoken(
        request_result["data"].get("ptoken") if request_result else ""
    )
    logger.info(f"ptoken: {ptoken}")
    payload["ptoken"] = ptoken
    payload["orderCreateUrl"] = "https://show.bilibili.com/api/ticket/order/createV2"
    url += "&ptoken=" + ptoken
    return url, payload


def buy_stream(
    tickets_info,
    time_start,
    interval,
    notifier_config,
    https_proxys,
    show_random_message=True,
    show_qrcode=True,
    use_local_token=False,
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

        return BuyStreamEvent(
            kind=kind,
            message=message,
            state=copy.deepcopy(state),
            data=data,
        )

    def handle_proxy_failure(
        reason: str,
        *,
        attempt: int | None = None,
    ):
        immediate_message, delay_seconds = _handle_proxy_failure(
            _request,
            reason,
            proxy_backoff,
            notifier_config,
        )
        attempt_total = (
            CREATE_RETRY_LIMIT if attempt is not None else state.attempt_total
        )
        if immediate_message:
            for message in immediate_message.splitlines():
                yield emit(
                    "proxy",
                    message,
                    current_proxy=_request.current_proxy_status(),
                    proxy_pool=_request.proxy_pool_status(),
                    cooldown_remaining=None,
                    status="running",
                    attempt_current=attempt,
                    attempt_total=attempt_total,
                )
        if delay_seconds is None:
            return
        for remaining in range(delay_seconds, 0, -1):
            yield emit(
                "state",
                None,
                current_proxy=_request.current_proxy_status(),
                proxy_pool=_request.proxy_pool_status(),
                cooldown_remaining=remaining,
                status="cooldown",
                attempt_current=attempt,
                attempt_total=attempt_total,
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
                attempt_total=attempt_total,
            )

    def handle_non_json_response(
        prefix: str,
        response,
        *,
        attempt: int | None = None,
    ) -> Generator[object, None, bool]:
        diagnostic = _request.describe_non_json_response(response)
        summary = _summarize_non_json_response(prefix, diagnostic)
        # 出现 412 风控时，走代理失败处理，切换代理或进入冷却等待。
        if "412 风控" in summary:
            yield emit(
                "proxy",
                f"{prefix}触发 412 风控",
                current_proxy=_request.current_proxy_status(),
                proxy_pool=_request.proxy_pool_status(),
                attempt_current=attempt,
                attempt_total=(
                    CREATE_RETRY_LIMIT if attempt is not None else state.attempt_total
                ),
            )
            yield from handle_proxy_failure(f"{prefix} 412 风控", attempt=attempt)
            return True
        yield emit(
            "attempt" if attempt is not None else "error",
            summary,
            current_proxy=_request.current_proxy_status(),
            proxy_pool=_request.proxy_pool_status(),
            attempt_current=attempt,
            attempt_total=(
                CREATE_RETRY_LIMIT if attempt is not None else state.attempt_total
            ),
        )
        return False

    isRunning = True
    tickets_info = json.loads(tickets_info)
    detail = tickets_info["detail"]
    cookies = tickets_info["cookies"]
    tickets_info.pop("cookies", None)
    tickets_info["_prepare_buyer_info"] = copy.deepcopy(tickets_info["buyer_info"])
    tickets_info["buyer_info"] = json.dumps(tickets_info["buyer_info"])
    tickets_info["deliver_info"] = json.dumps(tickets_info["deliver_info"])
    masked_proxies = ProxyManager.mask_proxy_string(https_proxys)
    logger.info(f"目前已配置代理：{masked_proxies or '直连'}")
    # requenst
    browser_window_state = generate_browser_window_state()
    _request = BiliRequest(
        cookies=cookies, proxy=https_proxys, browser_state=browser_window_state
    )
    proxy_backoff = ProxyBackoff()
    timeoffset = time_service.get_timeoffset()
    is_hot_project = bool(tickets_info.get("is_hot_project", False))
    use_local_token = bool(use_local_token)
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
            request_result: dict | None = None
            ticket_collection: CTokenRuntimeState = init_ctoken_state(
                browser_window_state=browser_window_state,
                ticket_collection_t=current_time_ms(timeoffset=timeoffset),
                href_length=len(
                    f"https://mall.bilibili.com/neul-next/ticket-renovation/detail.html?id={tickets_info['project_id']}&noTitleBar=1&from=pc_order_detail"
                ),
                user_agent_length=len(_request.get_user_agent()),
            )
            ticket_collection.touch(min_count=5, max_count=20)
            if is_hot_project:
                # hot
                yield emit("stage", "开始准备订单", stage="订单准备")
                token_payload["token"] = ticket_collection.snapshot().generate_ctoken()
                logger.info(f"itoken: {token_payload['token']}")
                request_result_normal = _request.post(
                    url=f"{base_url}/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                    data=token_payload,
                    isJson=True,
                )
                try:
                    request_result = request_result_normal.json()
                except JSONDecodeError:
                    yield from handle_non_json_response(
                        "订单准备接口",
                        request_result_normal,
                    )
                    continue
                proxy_backoff.reset()
                yield emit(
                    "status",
                    _format_status_result(
                        "订单准备结果",
                        request_result,  # type: ignore
                    ),
                )
                order_token = request_result["data"]["token"]  # type: ignore
                logger.info(f"token: {order_token}")

                # createTime
            else:
                # normal
                yield emit("status", None, stage="订单准备")
                if use_local_token:
                    order_token = _build_order_token(tickets_info)
                    yield emit(
                        "status",
                        "已启用本地 token 模式，跳过 prepare",
                    )
                else:
                    request_result_normal = _request.post(
                        url=f"{base_url}/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                        data=token_payload,
                        isJson=True,
                    )
                    try:
                        request_result = request_result_normal.json()
                    except JSONDecodeError:
                        yield from handle_non_json_response(
                            "订单准备接口",
                            request_result_normal,
                        )
                        continue
                    proxy_backoff.reset()
                    yield emit(
                        "status",
                        _format_status_result("订单准备结果", request_result),
                    )
                    order_token = request_result["data"]["token"]  # type: ignore

            yield emit(
                "stage",
                "开始创建订单",
                stage="创建订单",
                attempt_current=None,
                attempt_total=CREATE_RETRY_LIMIT,
            )
            result = None
            retry_outcome = RetryOutcome()
            token_expired = False
            attempt = 1
            _request.createTime = current_time_ms(timeoffset=timeoffset)
            while attempt <= CREATE_RETRY_LIMIT:
                batch_end = min(
                    attempt + CREATE_REQUEST_BATCH_SIZE - 1,
                    CREATE_RETRY_LIMIT,
                )
                ticket_collection.touch(min_count=2, max_count=5)  # 写订单中
                url, payload = _prepare_create_request(
                    _request,
                    ticket_collection,
                    tickets_info,
                    order_token,
                    timeoffset=timeoffset,
                    is_hot_project=is_hot_project,
                    request_result=request_result,
                )
                while attempt <= batch_end:
                    if not isRunning:
                        yield "抢票结束"
                        break
                    try:
                        try:
                            ticket_collection.touch(1)  # 写订单中
                            create_response = _request.post(
                                url=url,
                                data=payload,
                                isJson=True,
                            )
                            ret = create_response.json()
                        except JSONDecodeError as exc:
                            handled_412 = yield from handle_non_json_response(
                                "创建订单接口",
                                create_response,
                                attempt=attempt,
                            )
                            if not handled_412:
                                retry_outcome.set_exception(exc)
                            attempt += 1
                            time.sleep(interval / 1000)
                            continue
                        proxy_backoff.reset()
                        err = int(ret.get("errno", ret.get("code")))
                        retry_outcome.set_response(err, ret)
                        if _is_create_success(ret, err):
                            yield emit(
                                "success",
                                "创建订单成功",
                                attempt_current=attempt,
                                attempt_total=CREATE_RETRY_LIMIT,
                            )
                            result = (ret, err)
                            break
                        if err == 100051:
                            yield emit("status", "token过期，需要重新准备订单")
                            token_expired = True
                            break

                        yield emit(
                            "attempt",
                            ErrorCodes.format_attempt_result(err, ret),
                            attempt_current=attempt,
                            attempt_total=CREATE_RETRY_LIMIT,
                        )
                        if err == 100034:
                            yield emit(
                                "status",
                                f"更新票价为：{ret['data']['pay_money'] / 100}",
                                attempt_current=attempt,
                                attempt_total=CREATE_RETRY_LIMIT,
                            )
                            tickets_info["pay_money"] = ret["data"]["pay_money"]
                        ticket_collection.visibility_change(probability=0.1)

                    except RequestException as e:
                        retry_outcome.set_exception(e)
                        for message in handle_proxy_failure(
                            f"创建订单请求异常({e.__class__.__name__})",
                            attempt=attempt,
                        ):
                            yield message
                        yield emit(
                            "attempt",
                            str(e),
                            attempt_current=attempt,
                            attempt_total=CREATE_RETRY_LIMIT,
                        )

                    except Exception as e:
                        retry_outcome.set_exception(e)
                        yield emit(
                            "attempt",
                            str(e),
                            attempt_current=attempt,
                            attempt_total=CREATE_RETRY_LIMIT,
                        )

                    if result is not None or token_expired:
                        break
                    attempt += 1
                    time.sleep(randint(100, 300) / 1000)

                time.sleep(interval / 1000)
                if result is not None or token_expired or not isRunning:
                    break

                yield emit(
                    "status",
                    "本批次创建订单未成功，重新准备 CreateV2 请求",
                    attempt_current=None,
                    attempt_total=CREATE_RETRY_LIMIT,
                )
            else:
                if show_random_message:
                    yield emit("status", f"群友说👴： {get_random_fail_message()}")
                yield emit(
                    "status",
                    None,
                    attempt_current=None,
                    attempt_total=CREATE_RETRY_LIMIT,
                )
                continue
            if result is None:
                yield emit(
                    "status",
                    "本轮创建订单未成功，"
                    f"{_format_retry_reason(retry_outcome)}，重新准备订单",
                )
                continue

            # win了
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
                    "抢票成功，弹出付款二维码",
                    stage="抢票成功",
                    status="succeeded",
                )
                qrcode_url = get_qrcode_url(
                    _request,
                    request_result["data"]["orderId"],  # type: ignore
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
        except (HTTPError, RequestException) as e:
            logger.exception(e)
            yield emit("error", f"请求错误: {e}")
            for message in handle_proxy_failure(
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
    use_local_token=False,
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
        use_local_token=use_local_token,
    ):
        if msg.message is not None:
            logger.info(msg.message)


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
    use_local_token=False,
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
    if use_local_token:
        command.extend(["--use_local_token"])
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
