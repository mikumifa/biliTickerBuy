import json
import os
import subprocess
import sys
import time
import uuid
import copy
import webbrowser
from collections.abc import Generator
from json import JSONDecodeError
import shutil
import qrcode
from loguru import logger

from requests import HTTPError, RequestException
from cptoken import (
    generate_browser_window_state,
    init_ctoken_state,
)

from util.Notifier import NotifierManager, NotifierConfig
from util.ProxyBackoff import ProxyBackoff
from util.BiliRequest import BiliRequest
from util.ProxyManager import ProxyManager
from util.RandomMessages import get_random_fail_message
from util.TimeUtil import current_time_ms
from util.error_codes import ErrorCodes
from interface.project import fetch_project_payload
from task.buy_helpers import (
    BASE_URL as base_url,
    DEFAULT_CREATE_REQUEST_BATCH_SIZE,
    DEFAULT_CREATE_RETRY_LIMIT,
    DEFAULT_OUTER_LOOP_INTERVAL,
    build_order_token as _build_order_token,
    build_token_payload as _build_token_payload,
    create_order_terminal_rule as _create_order_terminal_rule,
    extract_order_id as _extract_order_id,
    format_retry_reason as _format_retry_reason,
    format_status_result as _format_status_result,
    get_order_detail_url,
    get_qrcode_url,
    handle_proxy_failure as _handle_proxy_failure,
    is_create_success as _is_create_success,
    prepare_create_request as _prepare_create_request,
    summarize_non_json_response as _summarize_non_json_response,
    wait_until_start as _wait_until_start,
)
from task.buy_types import (
    BuyStreamEvent,
    BuyStreamState,
    BuyStreamUpdate,
    BuyStreamWorker,
    CreateOrderTerminalRule,
    RetryOutcome,
)


def start_buy_stream_worker(*args, **kwargs) -> BuyStreamWorker:
    return BuyStreamWorker(buy_stream, *args, **kwargs).start()


def buy_stream(
    tickets_info,
    time_start,
    interval,
    notifier_config,
    https_proxys,
    show_random_message=True,
    show_qrcode=True,
    use_local_token=False,
    create_retry_limit: int = DEFAULT_CREATE_RETRY_LIMIT,
    create_request_batch_size: int = DEFAULT_CREATE_REQUEST_BATCH_SIZE,
    outer_loop_interval: int = DEFAULT_OUTER_LOOP_INTERVAL,
    proxy_max_consecutive_failures: int = 2,
    proxy_cooldown_seconds: int = 180,
    proxy_backoff_max_seconds: int = 600,
    auto_open_payment_url: bool = False,
):
    state = BuyStreamState()

    def emit(
        kind: str,
        message: str | None,
        update: BuyStreamUpdate | None = None,
    ):
        if update is not None:
            update.apply_to(state)
        if message is not None:
            state.last_message = message

        return BuyStreamEvent(
            kind=kind,
            message=message,
            state=copy.deepcopy(state),
            data=update.to_dict() if update is not None else {},
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
            effective_retry_limit if attempt is not None else state.attempt_total
        )
        if immediate_message:
            for message in immediate_message.splitlines():
                yield emit(
                    "proxy",
                    message,
                    BuyStreamUpdate(
                        current_proxy=_request.current_proxy_status(),
                        proxy_pool=_request.proxy_pool_status(),
                        cooldown_remaining=None,
                        status="running",
                        attempt_current=attempt,
                        attempt_total=attempt_total,
                    ),
                )
        if delay_seconds is None:
            return
        for remaining in range(delay_seconds, 0, -1):
            yield emit(
                "state",
                None,
                BuyStreamUpdate(
                    current_proxy=_request.current_proxy_status(),
                    proxy_pool=_request.proxy_pool_status(),
                    cooldown_remaining=remaining,
                    status="cooldown",
                    attempt_current=attempt,
                    attempt_total=attempt_total,
                ),
            )
            time.sleep(1)
        if _request.ensure_active_proxy():
            proxy_backoff.reset()
            yield emit(
                "state",
                None,
                BuyStreamUpdate(
                    current_proxy=_request.current_proxy_status(),
                    proxy_pool=_request.proxy_pool_status(),
                    cooldown_remaining=None,
                    status="running",
                    attempt_current=attempt,
                    attempt_total=attempt_total,
                ),
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
                BuyStreamUpdate(
                    current_proxy=_request.current_proxy_status(),
                    proxy_pool=_request.proxy_pool_status(),
                    attempt_current=attempt,
                    attempt_total=(
                        effective_retry_limit
                        if attempt is not None
                        else state.attempt_total
                    ),
                ),
            )
            yield from handle_proxy_failure(f"{prefix} 412 风控", attempt=attempt)
            return True
        yield emit(
            "attempt" if attempt is not None else "error",
            summary,
            BuyStreamUpdate(
                current_proxy=_request.current_proxy_status(),
                proxy_pool=_request.proxy_pool_status(),
                attempt_current=attempt,
                attempt_total=(
                    effective_retry_limit
                    if attempt is not None
                    else state.attempt_total
                ),
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
    _request = BiliRequest(
        cookies=cookies,
        proxy=https_proxys,
        proxy_failure_threshold=proxy_max_consecutive_failures,
        proxy_cooldown_seconds=proxy_cooldown_seconds,
    )
    proxy_backoff = ProxyBackoff(max_seconds=proxy_backoff_max_seconds)
    is_hot_project = bool(tickets_info.get("is_hot_project", False))
    use_local_token = bool(use_local_token)
    browser_window_state = generate_browser_window_state()
    token_payload = _build_token_payload(tickets_info)
    inner_loop_interval = max(1, int(interval))
    effective_retry_limit = max(1, int(create_retry_limit))
    effective_batch_size = max(1, int(create_request_batch_size))
    effective_outer_loop_interval = max(0, int(outer_loop_interval))

    def refresh_hot_and_warm():
        nonlocal is_hot_project
        messages: list[str] = []
        payload = fetch_project_payload(
            request=_request, project_id=int(tickets_info["project_id"])
        )
        if bool(payload["hotProject"]) and not is_hot_project:
            is_hot_project = True
            tickets_info["is_hot_project"] = True
        _request.prewarm_h2_connection(f"{base_url}/")
        return messages

    for warm_message in refresh_hot_and_warm():
        yield emit("status", warm_message)

    for wait_state in _wait_until_start(time_start, warmup=refresh_hot_and_warm):
        wait_message = wait_state.get("message")
        countdown_value = wait_state.get("countdown")
        countdown_seconds = wait_state.get("countdown_seconds")
        stage_value = None
        if isinstance(wait_message, str) and wait_message.startswith("0)"):
            stage_value = "等待开票"
        yield emit(
            "status",
            wait_message,
            BuyStreamUpdate(
                stage=stage_value or state.stage,
                countdown=countdown_value or state.countdown,
                countdown_seconds=(
                    countdown_seconds
                    if countdown_seconds is not None
                    else state.countdown_seconds
                ),
            ),
        )
    yield emit(
        "proxy",
        f"当前代理: {_request.current_proxy_status()}",
        BuyStreamUpdate(
            current_proxy=_request.current_proxy_status(),
            proxy_pool=_request.proxy_pool_status(),
        ),
    )

    while isRunning:
        try:
            request_result: dict | None = None
            ticket_collection_t = current_time_ms()
            ticket_state = init_ctoken_state(
                browser_window_state=browser_window_state,
                href_length=len(
                    f"https://mall.bilibili.com/neul-next/ticket-renovation/detail.html?id={tickets_info['project_id']}"
                ),
                user_agent_length=len(_request.get_user_agent()),
                ticket_collection_t=ticket_collection_t,
            )
            if is_hot_project:
                # hot
                yield emit("stage", "开始准备订单", BuyStreamUpdate(stage="订单准备"))
                prepare_ctoken_state = ticket_state.snapshot(now_ms=ticket_collection_t)
                token_payload["token"] = prepare_ctoken_state.generate_prepare_ctoken()
                request_result_normal = _request.post(
                    url=f"{base_url}/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
                    data=token_payload,
                    isJson=True,
                )
                request_result = request_result_normal.json()
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

            else:
                # normal
                yield emit("status", None, BuyStreamUpdate(stage="订单准备"))
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
                    request_result = request_result_normal.json()
                    proxy_backoff.reset()
                    yield emit(
                        "status",
                        _format_status_result("订单准备结果", request_result),
                    )
                    order_token = request_result["data"]["token"]  # type: ignore

            yield emit(
                "stage",
                "开始创建订单",
                BuyStreamUpdate(
                    stage="创建订单",
                    attempt_current=None,
                    attempt_total=effective_retry_limit,
                ),
            )
            result = None
            retry_outcome = RetryOutcome()
            token_expired = False
            terminal_result: tuple[int, dict, CreateOrderTerminalRule] | None = None
            attempt = 1
            while attempt <= effective_retry_limit:
                batch_end = min(
                    attempt + effective_batch_size - 1,
                    effective_retry_limit,
                )
                url, payload = _prepare_create_request(
                    tickets_info,
                    order_token,
                    is_hot_project=is_hot_project,
                    request_result=request_result,
                    ticket_state=ticket_state,
                )
                while attempt <= batch_end:
                    if not isRunning:
                        yield emit("status", "抢票结束")
                        break
                    try:
                        create_response = _request.post(
                            url=url,
                            data=payload,
                            isJson=True,
                        )
                        ret = create_response.json()
                        proxy_backoff.reset()
                        err = int(ret.get("errno", ret.get("code")))
                        retry_outcome.set_response(err, ret)
                        if _is_create_success(ret, err):
                            yield emit(
                                "success",
                                "创建订单成功",
                                BuyStreamUpdate(
                                    attempt_current=attempt,
                                    attempt_total=effective_retry_limit,
                                ),
                            )
                            result = (ret, err)
                            break
                        yield emit(
                            "attempt",
                            ErrorCodes.format_attempt_result(err, ret),
                            BuyStreamUpdate(
                                attempt_current=attempt,
                                attempt_total=effective_retry_limit,
                            ),
                        )
                        terminal_rule = _create_order_terminal_rule(err)
                        if terminal_rule is not None:
                            terminal_result = (err, ret, terminal_rule)
                            yield emit(
                                "status",
                                ErrorCodes.append_response_message(
                                    err,
                                    terminal_rule.message,
                                    ret,
                                ),
                                BuyStreamUpdate(
                                    attempt_current=attempt,
                                    attempt_total=effective_retry_limit,
                                    status=terminal_rule.status,
                                ),
                            )
                            break
                        if err == 100051:
                            yield emit("status", "token过期，需要重新准备订单")
                            token_expired = True
                            break
                        if err == 100034:
                            yield emit(
                                "status",
                                f"更新票价为：{ret['data']['pay_money'] / 100}",
                                BuyStreamUpdate(
                                    attempt_current=attempt,
                                    attempt_total=effective_retry_limit,
                                ),
                            )
                            tickets_info["pay_money"] = ret["data"]["pay_money"]
                        time.sleep(inner_loop_interval / 1000)
                    except JSONDecodeError as exc:
                        handled_412 = yield from handle_non_json_response(
                            "创建订单接口",
                            create_response,
                            attempt=attempt,
                        )
                        if not handled_412:
                            retry_outcome.set_exception(exc)
                            time.sleep(inner_loop_interval / 1000)
                        attempt += 1
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
                            BuyStreamUpdate(
                                attempt_current=attempt,
                                attempt_total=effective_retry_limit,
                            ),
                        )
                    except Exception as e:
                        logger.exception(e)
                        retry_outcome.set_exception(e)
                        yield emit(
                            "attempt",
                            str(e),
                            BuyStreamUpdate(
                                attempt_current=attempt,
                                attempt_total=effective_retry_limit,
                            ),
                        )
                    if (
                        result is not None
                        or token_expired
                        or terminal_result is not None
                    ):
                        break
                    attempt += 1
                    time.sleep(inner_loop_interval / 1000)

                if (
                    result is not None
                    or token_expired
                    or terminal_result is not None
                    or not isRunning
                ):
                    break

                if effective_outer_loop_interval > 0:
                    time.sleep(effective_outer_loop_interval / 1000)
            else:
                if show_random_message:
                    yield emit("status", f"群友说👴： {get_random_fail_message()}")
                yield emit(
                    "status",
                    None,
                    BuyStreamUpdate(
                        attempt_total=effective_retry_limit,
                    ),
                )
                continue
            if result is None:
                if terminal_result is not None:
                    errno, terminal_ret, terminal_rule = terminal_result
                    order_id = _extract_order_id(terminal_ret)
                    if terminal_rule.expose_payment_url and order_id is not None:
                        payment_url = get_order_detail_url(order_id)
                        yield emit(
                            "payment_qr",
                            "PAYMENT_QR_URL={0}".format(payment_url),
                            BuyStreamUpdate(
                                payment_qr_url=payment_url,
                                status=terminal_rule.status,
                            ),
                        )
                        if auto_open_payment_url:
                            try:
                                webbrowser.open(payment_url)
                                yield emit(
                                    "status",
                                    "已自动打开现有订单链接",
                                    BuyStreamUpdate(
                                        payment_qr_url=payment_url,
                                        status=terminal_rule.status,
                                    ),
                                )
                            except Exception as exc:
                                yield emit("status", f"自动打开订单链接失败: {exc}")
                    break
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
                    BuyStreamUpdate(
                        stage="抢票成功",
                        status="succeeded",
                    ),
                )
                order_id = request_result["data"]["orderId"]  # type: ignore
                payment_url = get_order_detail_url(order_id)
                qrcode_url = get_qrcode_url(
                    _request,
                    order_id,
                )
                yield emit(
                    "payment_qr",
                    "PAYMENT_QR_URL={0}".format(payment_url),
                    BuyStreamUpdate(
                        payment_qr_url=payment_url,
                        status="succeeded",
                    ),
                )
                if auto_open_payment_url:
                    try:
                        webbrowser.open(payment_url)
                        yield emit(
                            "status",
                            "已自动打开支付链接",
                            BuyStreamUpdate(
                                payment_qr_url=payment_url,
                                status="succeeded",
                            ),
                        )
                    except Exception as exc:
                        yield emit("status", f"自动打开支付链接失败: {exc}")
                if show_qrcode:
                    qr_gen = qrcode.QRCode()
                    qr_gen.add_data(qrcode_url)
                    qr_gen.make(fit=True)
                    qr_gen_image = qr_gen.make_image()
                    qr_gen_image.show()  # type: ignore
                break
        except (HTTPError, RequestException) as e:
            logger.exception(e)
            yield emit("error", f"请求错误: {e}")
            for message in handle_proxy_failure(
                f"订单准备请求异常({e.__class__.__name__})"
            ):
                yield message
        except Exception as e:
            logger.exception(e)
            yield emit(
                "error",
                f"程序异常: {repr(e)}",
                BuyStreamUpdate(status="failed"),
            )


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
    create_retry_limit: int = DEFAULT_CREATE_RETRY_LIMIT,
    create_request_batch_size: int = DEFAULT_CREATE_REQUEST_BATCH_SIZE,
    outer_loop_interval: int = DEFAULT_OUTER_LOOP_INTERVAL,
    proxy_max_consecutive_failures: int = 2,
    proxy_cooldown_seconds: int = 180,
    proxy_backoff_max_seconds: int = 600,
    auto_open_payment_url: bool = False,
):
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
        create_retry_limit=create_retry_limit,
        create_request_batch_size=create_request_batch_size,
        outer_loop_interval=outer_loop_interval,
        proxy_max_consecutive_failures=proxy_max_consecutive_failures,
        proxy_cooldown_seconds=proxy_cooldown_seconds,
        proxy_backoff_max_seconds=proxy_backoff_max_seconds,
        auto_open_payment_url=auto_open_payment_url,
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
    show_qrcode=True,
    use_local_token=False,
    log_file_path: str | None = None,
    create_retry_limit: int = DEFAULT_CREATE_RETRY_LIMIT,
    create_request_batch_size: int = DEFAULT_CREATE_REQUEST_BATCH_SIZE,
    outer_loop_interval: int = DEFAULT_OUTER_LOOP_INTERVAL,
    proxy_max_consecutive_failures: int = 2,
    proxy_cooldown_seconds: int = 180,
    proxy_backoff_max_seconds: int = 600,
    auto_open_payment_url: bool = False,
    log_level: str | None = None,
    log_retention_days: int | None = None,
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
    command.extend(["--outer_interval", str(outer_loop_interval)])
    command.extend(["--create_retry_limit", str(create_retry_limit)])
    command.extend(["--create_request_batch_size", str(create_request_batch_size)])
    command.extend(
        ["--proxy_max_consecutive_failures", str(proxy_max_consecutive_failures)]
    )
    command.extend(["--proxy_cooldown_seconds", str(proxy_cooldown_seconds)])
    command.extend(["--proxy_backoff_max_seconds", str(proxy_backoff_max_seconds)])
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
    if not show_qrcode:
        command.extend(["--hide_qrcode"])
    if auto_open_payment_url:
        command.extend(["--auto_open_payment_url"])
    if use_local_token:
        command.extend(["--use_local_token"])
    env = os.environ.copy()
    env["BTB_PARENT_PID"] = str(os.getpid())
    if log_level:
        normalized_log_level = str(log_level).lower()
        if normalized_log_level == "simple":
            env["BTB_LOG_LEVEL"] = "INFO"
            env["BTB_CONSOLE_LOG_LEVEL"] = "INFO"
        elif normalized_log_level == "debug":
            env["BTB_LOG_LEVEL"] = "DEBUG"
            env["BTB_CONSOLE_LOG_LEVEL"] = "DEBUG"
        else:
            env["BTB_LOG_LEVEL"] = "DEBUG"
            env["BTB_CONSOLE_LOG_LEVEL"] = "INFO"
    if log_retention_days is not None:
        env["BTB_LOG_RETENTION_DAYS"] = str(log_retention_days)
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
