from __future__ import annotations

import datetime
import math
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from cptoken import CTokenRuntimeState, sim_ctoken_state

from util import time_service
from app_cmd.config.NotifierConfig import NotifierConfig
from util.Constant import (
    BASE_URL,
    BEIJING_TZ,
    WARMUP_AT_SECONDS,
)
from util.notifer.Notifier import NotifierManager
from util.proxy.ProxyBackoff import ProxyBackoff
from util.request.BiliRequest import BiliRequest
from util.request.TokenUtil import generate_token
from util.ErrorCodes import ErrorCodes

from .buy_types import CreateOrderTerminalRule, RetryOutcome


def get_qrcode_url(_request, order_id) -> str:
    url = f"{BASE_URL}/api/ticket/order/getPayParam?order_id={order_id}"
    data = _request.get(url).json()
    if data.get("errno", data.get("code")) == 0:
        return data["data"]["code_url"]
    raise ValueError("获取二维码失败")


def get_order_detail_url(order_id: int | str) -> str:
    return f"{BASE_URL}/platform/orderDetail.html?order_id={order_id}"


def build_order_detail_payment_result(order_id: int | str) -> dict[str, Any]:
    order_detail_url = get_order_detail_url(order_id)
    return {
        "order_id": order_id,
        "order_detail_url": order_detail_url,
        "payment_code_url": None,
        "payment_qr_url": order_detail_url,
    }


def build_payment_result(
    _request: BiliRequest,
    order_id: int | str,
) -> dict[str, Any]:
    payment_result = build_order_detail_payment_result(order_id)
    payment_result["payment_code_url"] = get_qrcode_url(_request, order_id)
    return payment_result


def build_payment_result_with_fallback(
    _request: BiliRequest,
    order_id: int | str,
) -> tuple[dict[str, Any], Exception | None]:
    try:
        return build_payment_result(_request, order_id), None
    except Exception as exc:
        return build_order_detail_payment_result(order_id), exc


def format_countdown(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days > 0:
        return f"{days}天{hours}小时{minutes}分{secs}秒"
    return f"{hours}小时{minutes}分{secs}秒"


def next_countdown_report_at(countdown_seconds: int) -> int:
    if countdown_seconds > 86400:
        return ((countdown_seconds - 1) // 86400) * 86400
    if countdown_seconds > 3600:
        return ((countdown_seconds - 1) // 3600) * 3600
    if countdown_seconds > 60:
        return ((countdown_seconds - 1) // 60) * 60
    if countdown_seconds > 10:
        return ((countdown_seconds - 1) // 10) * 10
    return -1


def wait_until_start(time_start: str, warmup=None):
    if not time_start:
        return

    timeoffset = time_service.get_timeoffset()
    yield {"message": "0) 等待开始时间"}
    yield {
        "message": (
            f"时间偏差已被设置为: {timeoffset}秒"
            f"（时间源: {getattr(time_service, 'time_source', 'unknown')}）"
        )
    }
    bili_check = time_service.compute_bili_time_check(attempts=2, timeout=1.5)
    if bili_check is not None:
        yield {
            "message": (
                "会员购Date校验: "
                f"与当前时间源差异约{bili_check.offset_center - timeoffset:+.3f}秒，"
                f"不确定度约±{bili_check.uncertainty_seconds:.3f}秒，"
                f"RTT {bili_check.delay * 1000:.1f}ms"
            )
        }
        yield {"message": "倒计时默认使用会员购 Date 时间源。"}

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

    yield {"message": f"计划抢票开始时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')}"}

    if hasattr(time_service, "countdown_now"):
        countdown_now = time_service.countdown_now
    else:
        countdown_now = time_service.now
    if hasattr(time_service, "countdown_time_source"):
        countdown_source = time_service.countdown_time_source
    else:

        def countdown_source():
            return getattr(time_service, "time_source", "unknown")

    yield {"message": f"倒计时时间源: {countdown_source()}"}
    time_difference = target_time.timestamp() - countdown_now()
    end_time = time.perf_counter() + time_difference
    next_report_at = float("inf")
    warmed = False
    last_countdown_seconds: int | None = None
    while True:
        remaining = end_time - time.perf_counter()
        if remaining <= 0:
            return
        countdown_seconds = max(0, math.ceil(remaining))
        countdown_text = format_countdown(remaining)
        if countdown_seconds != last_countdown_seconds:
            last_countdown_seconds = countdown_seconds
            yield {
                "message": None,
                "countdown": countdown_text,
                "countdown_seconds": countdown_seconds,
            }
        if not warmed and warmup is not None and remaining <= WARMUP_AT_SECONDS:
            warmed = True
            try:
                warm_messages = warmup() or []
            except Exception as exc:
                logger.warning(f"预热/复检失败（忽略）：{exc}")
                warm_messages = [f"预热/复检失败（忽略）：{exc}"]
            for warm_message in warm_messages:
                yield {
                    "message": warm_message,
                    "countdown": countdown_text,
                    "countdown_seconds": countdown_seconds,
                }
            continue
        if countdown_seconds <= next_report_at:
            if countdown_seconds > 10:
                yield {
                    "message": f"距离开始抢票还有: {countdown_text}",
                    "countdown": countdown_text,
                    "countdown_seconds": countdown_seconds,
                }
            next_report_at = next_countdown_report_at(countdown_seconds)
        time.sleep(min(0.5, remaining))


def build_token_payload(tickets_info: dict) -> dict:
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


def build_order_token(tickets_info: dict) -> str:
    return generate_token(
        project_id=int(tickets_info["project_id"]),
        screen_id=int(tickets_info["screen_id"]),
        order_type=int(tickets_info.get("order_type", 1)),
        count=int(tickets_info["count"]),
        sku_id=int(tickets_info["sku_id"]),
    )


def normalize_prepare_ptoken(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).replace("=", "")


CREATE_ORDER_TERMINAL_RULES: dict[int, CreateOrderTerminalRule] = {
    100003: CreateOrderTerminalRule(
        status="completed",
        message="该项目每人限购1张，已存在购买订单，停止重试",
    ),
    100048: CreateOrderTerminalRule(
        status="completed",
        message="有尚未完成订单，停止重试",
        expose_payment_url=True,
    ),
    100079: CreateOrderTerminalRule(
        status="completed",
        message="有重复订单，停止重试",
    ),
}


def create_order_terminal_rule(err: int) -> CreateOrderTerminalRule | None:
    return CREATE_ORDER_TERMINAL_RULES.get(err)


def is_create_success(ret: dict, err: int) -> bool:
    resp_message = str(ret.get("msg", ret.get("message", "")) or "")
    return err == 0 and "defaultBBR" not in resp_message


def extract_order_id(ret: dict | None) -> int | str | None:
    if not isinstance(ret, dict):
        return None
    data = ret.get("data")
    if not isinstance(data, dict):
        return None
    order_id = data.get("orderId")
    return order_id if order_id not in (None, "", 0) else None


def extract_response_message(ret: dict) -> str:
    return str(ret.get("msg", ret.get("message", "")) or "").strip()


def append_response_message(err: int, base: str, ret: dict | None) -> str:
    return ErrorCodes.append_response_message(err, base, ret)


def format_retry_reason(outcome: RetryOutcome) -> str:
    if outcome.exc is not None:
        return f"最后一次异常: {outcome.exc}"
    if outcome.err is None:
        return "最后一次失败原因未知"
    reason = ErrorCodes.get_message_or_unknown(outcome.err)
    detail = outcome.ret if outcome.ret is not None else {}
    base = f"最后一次返回: [{outcome.err}]({reason}) | {detail}"
    return append_response_message(outcome.err, base, outcome.ret)


def summarize_non_json_response(prefix: str, diagnostic: str) -> str:
    if "status=412" in diagnostic:
        return f"{prefix}触发 412 风控"

    content_type = "未知"
    for part in diagnostic.split(", "):
        if part.startswith("content_type="):
            content_type = part.split("=", 1)[1]
            break
    return f"{prefix}返回了非 JSON 响应（{content_type}）"


def build_proxy_exhausted_message(_request: BiliRequest, delay_seconds: int) -> str:
    return (
        "当前所有代理暂时不可用，请尽快补充或更换代理。"
        f"程序将休息 {delay_seconds} 秒后继续尝试。"
        f" 代理池状态：{_request.proxy_pool_status()}"
    )


def notify_proxy_exhausted(
    notifier_config: NotifierConfig,
    _request: BiliRequest,
    delay_seconds: int,
) -> None:
    if not notifier_config.notify_proxy_exhausted:
        return

    manager = NotifierManager.create_from_config(
        config=notifier_config,
        title="代理已全部失效",
        content=build_proxy_exhausted_message(_request, delay_seconds),
        include_audio=False,
    )
    manager.start_all()


def handle_proxy_failure(
    _request: BiliRequest,
    reason: str,
    proxy_backoff: ProxyBackoff,
    notifier_config: NotifierConfig,
    replenish_proxy_pool: Callable[[], tuple[bool, str | None]] | None = None,
) -> tuple[str | None, int | None]:
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

    if replenish_proxy_pool is not None:
        replenished, replenish_message = replenish_proxy_pool()
        if replenished:
            proxy_backoff.reset()
            if immediate_message and replenish_message:
                return f"{immediate_message}\n{replenish_message}", None
            return replenish_message or immediate_message, None
        if replenish_message:
            immediate_message = (
                f"{immediate_message}\n{replenish_message}"
                if immediate_message
                else replenish_message
            )

    delay_seconds = proxy_backoff.next_delay_seconds()
    if proxy_backoff.should_notify():
        notify_proxy_exhausted(notifier_config, _request, delay_seconds)
    exhausted_message = f"所有代理当前不可用，休息 {delay_seconds} 秒后再试"
    if immediate_message:
        return f"{immediate_message}\n{exhausted_message}", delay_seconds
    return exhausted_message, delay_seconds


def format_status_result(prefix: str, ret: dict) -> str:
    err = int(ret.get("errno", ret.get("code", -1)))
    reason = ErrorCodes.get_message(err)
    if reason:
        return append_response_message(err, f"{prefix}: [{err}] {reason}", ret)
    message = extract_response_message(ret)
    if message:
        return f"{prefix}: [{err}] {message}"
    return f"{prefix}: [{err}] {ret}"


def prepare_create_request(
    tickets_info: dict,
    order_token: str,
    is_hot_project: bool,
    request_result: dict | None,
    ticket_state: CTokenRuntimeState,
) -> tuple[str, dict]:
    payload = dict(tickets_info)
    payload["again"] = 1
    payload["token"] = order_token
    now_ms = time_service.current_time_ms()
    payload["timestamp"] = now_ms
    payload["newRisk"] = True
    payload["requestSource"] = "neul-next"
    payload.pop("detail", None)
    payload.pop("sale_start", None)
    payload.pop("username", None)
    payload.pop("_prepare_buyer_info", None)
    url = (
        f"{BASE_URL}/api/ticket/order/createV2?project_id={tickets_info['project_id']}"
    )

    # if not is_hot_project:
    #     return url, payload
    create_state = sim_ctoken_state(
        before_state=ticket_state,
        now_ms=now_ms,
    )
    payload["ctoken"] = create_state.generate_create_ctoken()
    prepare_data = request_result.get("data", {}) if request_result else {}
    ptoken = normalize_prepare_ptoken(prepare_data.get("ptoken"))
    payload["ptoken"] = ptoken
    payload["orderCreateUrl"] = "https://show.bilibili.com/api/ticket/order/createV2"
    url += "&ptoken=" + ptoken
    return url, payload
