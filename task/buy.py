import json
import os
import random
import subprocess
import sys
import time
import uuid
import copy
import webbrowser
from collections.abc import Generator
from dataclasses import dataclass
from json import JSONDecodeError
import shutil
import qrcode
from loguru import logger

from requests import HTTPError, RequestException
from cptoken import (
    generate_browser_window_state,
    init_ctoken_state,
)

from app_cmd.config.BuyConfig import BuyConfig
from interface.project import fetch_project_payload
from util.notifer.Notifier import NotifierManager
from util.proxy.ProxyBackoff import ProxyBackoff
from util.proxy.ProxyManager import ProxyManager
from util.notifer.RandomMessages import get_random_fail_message
from util.TimeUtil import current_time_ms
from util.ErrorCodes import ErrorCodes
from task.buy_helpers import (
    BASE_URL as base_url,
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
from util.request.BiliRequest import BiliRequest
from util.request.exceptions import BiliConnectionError, BiliRateLimitError


@dataclass(slots=True)
class Buy:
    config: BuyConfig

    def _resolved_tickets_info(self) -> str:
        if self.config.config_file:
            config_path = os.path.expanduser(self.config.config_file)
            with open(config_path, "r", encoding="utf-8") as config_file:
                return config_file.read()
        return self.config.tickets_info

    def resolved_config(self) -> BuyConfig:
        return self.config.with_overrides(
            tickets_info=self._resolved_tickets_info(),
        )

    def stream(self):
        yield from buy_stream(self.resolved_config())

    def start_worker(self) -> BuyStreamWorker:
        return BuyStreamWorker.start_buy_stream_worker(self.stream)

    def to_cli_args(self) -> list[str]:
        if self.config.config_file:
            return [
                "buy",
                "--config-file",
                self.config.config_file,
                *self.config.to_cli_args(),
            ]
        return [
            "buy",
            "--tickets-info",
            self.config.tickets_info,
            *self.config.to_cli_args(),
        ]

    def run(self, on_message=None) -> None:
        worker = self.start_worker()
        for event in worker.iter_events():
            if event.message is not None and on_message is not None:
                on_message(event.message)

    def buy(self) -> None:
        self.run(logger.info)

    def start_new_terminal(
        self,
        *,
        log_file_path: str | None = None,
        log_level: str | None = None,
        log_retention_days: int | None = None,
    ) -> subprocess.Popen:
        command = None

        if getattr(sys, "frozen", False):
            command = [sys.executable]
        else:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            main_py = os.path.join(script_dir, "main.py")

            if os.path.exists(main_py):
                command = [sys.executable, main_py]
            else:
                btb_path = shutil.which("btb")
                if not btb_path:
                    raise RuntimeError("Cannot find main.py or btb command")
                command = [btb_path]
        command.extend(self.to_cli_args())
        env = os.environ.copy()
        env["BTB_PARENT_PID"] = str(os.getpid())
        effective_log_level = log_level or self.config.log_level
        if effective_log_level:
            normalized_log_level = str(effective_log_level).lower()
            if normalized_log_level == "simple":
                env["BTB_LOG_LEVEL"] = "INFO"
                env["BTB_CONSOLE_LOG_LEVEL"] = "INFO"
            elif normalized_log_level == "debug":
                env["BTB_LOG_LEVEL"] = "DEBUG"
                env["BTB_CONSOLE_LOG_LEVEL"] = "DEBUG"
            else:
                env["BTB_LOG_LEVEL"] = "DEBUG"
                env["BTB_CONSOLE_LOG_LEVEL"] = "INFO"
        env["BTB_LOG_RETENTION_DAYS"] = str(
            log_retention_days
            if log_retention_days is not None
            else self.config.log_retention_days
        )
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
            return subprocess.Popen(command, env=env, **kwargs)

        with open(os.devnull, "r") as devnull_in, open(os.devnull, "a") as devnull_out:
            return subprocess.Popen(
                command,
                env=env,
                stdin=devnull_in,
                stdout=devnull_out,
                stderr=devnull_out,
                **kwargs,
            )

    def buy_new_terminal(
        self,
        *,
        log_file_path: str | None = None,
        log_level: str | None = None,
        log_retention_days: int | None = None,
    ) -> subprocess.Popen:
        return self.start_new_terminal(
            log_file_path=log_file_path,
            log_level=log_level,
            log_retention_days=log_retention_days,
        )


def _extract_prepare_token(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if token is None:
        return None
    token = str(token).strip()
    return token or None


def _format_reprepare_reason(reason: str) -> str:
    return f"重新准备订单，原因：{reason}"


def buy_stream(config: BuyConfig):
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
            config.notifier_config,
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
    tickets_info = json.loads(config.tickets_info)
    detail = tickets_info["detail"]
    cookies = tickets_info["cookies"]
    tickets_info.pop("cookies", None)
    tickets_info["_prepare_buyer_info"] = copy.deepcopy(tickets_info["buyer_info"])
    tickets_info["buyer_info"] = json.dumps(tickets_info["buyer_info"])
    tickets_info["deliver_info"] = json.dumps(tickets_info["deliver_info"])
    masked_proxies = ProxyManager.mask_proxy_string(config.https_proxys)
    logger.info(f"目前已配置代理：{masked_proxies or '直连'}")
    _request = BiliRequest(
        cookies=cookies,
        proxy=config.https_proxys,
        proxy_failure_threshold=config.proxy_max_consecutive_failures,
        proxy_cooldown_seconds=config.proxy_cooldown_seconds,
    )
    proxy_backoff = ProxyBackoff(max_seconds=config.proxy_backoff_max_seconds)
    is_hot_project = bool(tickets_info.get("is_hot_project", False))
    # use_local_token = bool(config.use_local_token)
    browser_window_state = generate_browser_window_state()
    token_payload = _build_token_payload(tickets_info)
    request_interval = max(1, int(config.interval or 1000))
    effective_retry_limit = max(1, int(config.create_retry_limit))
    effective_batch_size = max(1, int(config.create_request_batch_size))
    rate_limit_delay_ms = max(0, int(config.rate_limit_delay_ms))

    def emit_reprepare(reason: str):
        message = _format_reprepare_reason(reason)
        logger.info(message)
        return emit("status", message)

    def refresh_hot_and_warm():
        nonlocal is_hot_project
        logger.info("预热/复检：开始拉取项目详情并预热连接")
        payload = fetch_project_payload(
            request=_request, project_id=int(tickets_info["project_id"])
        )
        if bool(payload["hotProject"]) and not is_hot_project:
            is_hot_project = True
            tickets_info["is_hot_project"] = True
            logger.info("预热/复检：检测到 hotProject=True，已升级为 hot 抢票策略")
        else:
            logger.info("预热/复检完成。")
        _request.prewarm_h2_connection(f"{base_url}/")

    # 循环内主动复检项目详情：按随机 create 次数触发纯拉取，与 100001 路径共享计数。
    # fetch 落在两次 create 的 sleep 窗口，不与 create 并发。
    refresh_min_count = max(0, int(config.refresh_interval_min_count))
    refresh_max_count = max(0, int(config.refresh_interval_max_count))
    refresh_count_enabled = (
        refresh_max_count > 0 and refresh_min_count <= refresh_max_count
    )
    refresh_counter = 0
    refresh_target = (
        random.randint(refresh_min_count, refresh_max_count)
        if refresh_count_enabled
        else None
    )

    def _reset_refresh_counter():
        """重置计数器并重抽下一次目标次数。定时与 100001 两路径共用。"""
        nonlocal refresh_counter, refresh_target
        refresh_counter = 0
        if refresh_count_enabled:
            refresh_target = random.randint(refresh_min_count, refresh_max_count)

    def _on_100001():
        refresh_hot_and_warm()
        _reset_refresh_counter()

    _request.set_100001_handler(_on_100001)

    refresh_hot_and_warm()

    yield emit(
        "proxy",
        f"当前代理: {_request.current_proxy_status()}",
        BuyStreamUpdate(
            current_proxy=_request.current_proxy_status(),
            proxy_pool=_request.proxy_pool_status(),
        ),
    )

    for wait_state in _wait_until_start(
        config.time_start,
        warmup=refresh_hot_and_warm,
    ):
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
            # if is_hot_project:
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
            order_token = _extract_prepare_token(request_result)
            if not order_token:
                yield emit_reprepare("订单准备未返回有效 token")
                continue
            # else:
            #     # normal
            #     yield emit("status", None, BuyStreamUpdate(stage="订单准备"))
            #     if use_local_token:
            #         order_token = _build_order_token(tickets_info)
            #         yield emit(
            #             "status",
            #             "已启用本地 token 模式，跳过 prepare",
            #         )
            #     else:
            #         request_result_normal = _request.post(
            #             url=f"{base_url}/api/ticket/order/prepare?project_id={tickets_info['project_id']}",
            #             data=token_payload,
            #             isJson=True,
            #         )
            #         request_result = request_result_normal.json()
            #         proxy_backoff.reset()
            #         yield emit(
            #             "status",
            #             _format_status_result("订单准备结果", request_result),
            #         )
            #         order_token = _extract_prepare_token(request_result)
            #         if not order_token:
            #             yield emit_reprepare("订单准备未返回有效 token")
            #             time.sleep(request_interval / 1000)
            #             continue

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
                    should_sleep_before_next_attempt = False
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
                        _request.handle_100001(err)
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
                            yield emit_reprepare("token过期")
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
                        should_sleep_before_next_attempt = True
                    except JSONDecodeError as exc:
                        handled_412 = yield from handle_non_json_response(
                            "创建订单接口",
                            create_response,
                            attempt=attempt,
                        )
                        if not handled_412:
                            retry_outcome.set_exception(exc)
                    except BiliRateLimitError as e:
                        retry_outcome.set_exception(e)
                        yield emit(
                            "attempt",
                            (
                                f"{e}，延迟 {rate_limit_delay_ms}ms 后继续"
                                if rate_limit_delay_ms > 0
                                else str(e)
                            ),
                            BuyStreamUpdate(
                                attempt_current=attempt,
                                attempt_total=effective_retry_limit,
                            ),
                        )
                        if rate_limit_delay_ms > 0:
                            time.sleep(rate_limit_delay_ms / 1000)
                        continue  # 不需要sleep
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
                    finally:
                        attempt += 1

                    if (
                        result is not None
                        or token_expired
                        or terminal_result is not None
                    ):
                        break
                    # 按随机 create 次数主动复检项目详情（纯拉取，落在 sleep 窗口，不与 create 并发）
                    if refresh_count_enabled and refresh_target is not None:
                        refresh_counter += 1
                        if refresh_counter >= refresh_target:
                            try:
                                refresh_hot_and_warm()
                            except Exception as exc:
                                logger.warning(f"循环内项目详情复检失败（忽略）：{exc}")
                            _reset_refresh_counter()
                    if should_sleep_before_next_attempt:
                        time.sleep(request_interval / 1000)

                if (
                    result is not None
                    or token_expired
                    or terminal_result is not None
                    or not isRunning
                ):
                    break

            else:
                if config.show_random_message:
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
                        if config.auto_open_payment_url:
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
                reason = _format_retry_reason(retry_outcome)
                yield emit(
                    "status",
                    f"本轮创建订单未成功，{reason}",
                )
                yield emit_reprepare(reason)
                continue
            # win了
            request_result, errno = result
            if errno == 0:
                notifierManager = NotifierManager.create_from_config(
                    config=config.notifier_config,
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
                if config.auto_open_payment_url:
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
                if config.show_qrcode:
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
        except BiliRateLimitError as e:
            logger.warning(str(e))
            yield emit(
                "error",
                (
                    f"{e}，延迟 {rate_limit_delay_ms}ms 后重试准备订单"
                    if rate_limit_delay_ms > 0
                    else str(e)
                ),
            )
            if rate_limit_delay_ms > 0:
                time.sleep(rate_limit_delay_ms / 1000)
            yield emit_reprepare("订单准备阶段触发 HTTP 429")
        except BiliConnectionError as e:
            logger.warning(str(e))
            yield emit(
                "error",
                str(e),
            )
        except Exception as e:
            logger.exception(e)
            yield emit(
                "error",
                f"程序异常: {repr(e)}",
                BuyStreamUpdate(status="failed"),
            )


def buy_new_terminal(
    config: BuyConfig,
    log_file_path: str | None = None,
    log_level: str | None = None,
    log_retention_days: int | None = None,
) -> subprocess.Popen:
    return Buy(config=config).buy_new_terminal(
        log_file_path=log_file_path,
        log_level=log_level,
        log_retention_days=log_retention_days,
    )
