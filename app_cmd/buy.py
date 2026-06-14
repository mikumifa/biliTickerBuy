from argparse import Namespace
import os
import re
import sys
import time

from util.task_markers import TASK_STOPPED_MARKER


def buy_cmd(args: Namespace):
    from util.LogConfig import loguru_config
    import uuid

    from util import LOG_DIR
    from task.buy import buy, buy_stream
    from util.Notifier import NotifierConfig
    from util.terminal_renderer import (
        TerminalRenderContext,
        create_terminal_renderer,
        render_message_stream,
    )
    from loguru import logger

    console_close_handler_ref = None

    def load_tickets_info(tickets_info: str) -> tuple[str, str | None]:
        config_path = os.path.expanduser(tickets_info)
        if os.path.isfile(config_path):
            logger.info(f"使用配置文件：{config_path}")
            try:
                with open(config_path, "r", encoding="utf-8") as config_file:
                    return config_file.read(), config_path
            except OSError as exc:
                raise SystemExit(f"读取配置文件失败: {exc}") from exc
        return tickets_info, None

    def resolve_log_file_name() -> str:
        configured_name = os.environ.get("BTB_APP_LOG_NAME", "").strip()
        if configured_name:
            return re.sub(r"[^\w.\-]", "_", os.path.basename(configured_name))
        return f"{uuid.uuid4()}.log"

    def hold_terminal(message: str) -> None:
        try:
            if os.name == "nt":
                import msvcrt

                print(message, flush=True)
                msvcrt.getwch()
                return

            if not sys.stdin or not sys.stdin.isatty():
                return
            input(message)
        except (EOFError, KeyboardInterrupt):
            pass

    def hold_terminal_after_interrupt():
        hold_terminal("已停止当前抢票流程。按任意键关闭此窗口...")

    def hold_terminal_after_finish() -> None:
        if os.environ.get("BTB_HOLD_TERMINAL", "") != "1":
            return
        hold_terminal("抢票流程已结束。按任意键关闭此窗口...")

    def hold_terminal_after_error(message: str) -> None:
        if os.environ.get("BTB_HOLD_TERMINAL", "") != "1":
            return
        hold_terminal(f"{message}\n按任意键关闭此窗口...")

    def install_console_close_handler() -> None:
        nonlocal console_close_handler_ref
        if os.name != "nt":
            return
        import ctypes

        ctrl_close_event = 2
        ctrl_logoff_event = 5
        ctrl_shutdown_event = 6

        handler_routine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

        @handler_routine
        def _handler(ctrl_type):
            if ctrl_type in {
                ctrl_close_event,
                ctrl_logoff_event,
                ctrl_shutdown_event,
            }:
                try:
                    logger.warning(TASK_STOPPED_MARKER)
                    logger.warning("检测到终端被用户主动关闭，任务即将结束。")
                except Exception:
                    pass
                time.sleep(0.1)
                return False
            return False

        ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler, True)
        console_close_handler_ref = _handler

    def exit_immediately_if_child_process() -> None:
        if child_process_mode:
            os._exit(0)

    def build_notifier_config() -> NotifierConfig:
        return NotifierConfig(
            serverchan_key=args.serverchanKey,
            serverchan3_api_url=args.serverchan3ApiUrl,
            pushplus_token=args.pushplusToken,
            bark_token=args.barkToken,
            ntfy_url=args.ntfy_url,
            ntfy_username=args.ntfy_username,
            ntfy_password=args.ntfy_password,
            meow_nickname=args.meowNickname,
            audio_path=args.audio_path,
            notify_proxy_exhausted=args.notify_proxy_exhausted,
        )

    def run_with_terminal_renderer(tickets_info: str):
        renderer = create_terminal_renderer(
            TerminalRenderContext(
                config_name=filename_only,
                log_file=log_file,
                platform_name=os.name,
            ),
            prefer_rich=os.name == "nt",
        )
        render_message_stream(
            renderer,
            buy_stream(
                tickets_info,
                args.time_start,
                args.interval,
                build_notifier_config(),
                args.https_proxys,
                not args.hide_random_message,
                readable=True,
                use_local_ptoken=args.use_local_ptoken,
            ),
            on_message=logger.info,
        )

    tickets_info, config_path = load_tickets_info(args.tickets_info)
    filename = os.path.basename(config_path) if config_path else "default"
    filename_only = os.path.basename(filename)
    log_file_name = resolve_log_file_name()
    child_process_mode = os.environ.get("BTB_CHILD_PROCESS", "") == "1"
    use_terminal_renderer = os.name == "nt" and not child_process_mode
    enable_console_log = not use_terminal_renderer and not child_process_mode
    log_file = loguru_config(
        LOG_DIR,
        log_file_name,
        enable_console=enable_console_log,
    )
    install_console_close_handler()
    if enable_console_log:
        logger.info(f"抢票日志路径：{log_file}")
    try:
        if use_terminal_renderer:
            run_with_terminal_renderer(tickets_info)
        else:
            buy(
                tickets_info,
                args.time_start,
                args.interval,
                args.audio_path,
                args.pushplusToken,
                args.serverchanKey,
                args.barkToken,
                args.https_proxys,
                args.serverchan3ApiUrl,
                args.ntfy_url,
                args.ntfy_username,
                args.ntfy_password,
                args.meowNickname,
                args.notify_proxy_exhausted,
                not args.hide_random_message,
                use_local_ptoken=args.use_local_ptoken,
            )
    except KeyboardInterrupt:
        logger.warning("收到 Ctrl+C，已停止当前抢票流程。")
        exit_immediately_if_child_process()
        hold_terminal_after_interrupt()
        return
    except SystemExit as exc:
        if exc.code in (None, 0):
            raise
        logger.error(f"抢票流程异常退出: {exc.code}")
        if os.environ.get("BTB_HOLD_TERMINAL", "") == "1":
            hold_terminal_after_error(f"抢票流程异常退出: {exc.code}")
            return
        raise
    except Exception as exc:
        logger.exception("抢票流程异常退出")
        if os.environ.get("BTB_HOLD_TERMINAL", "") == "1":
            hold_terminal_after_error(f"抢票流程异常退出: {exc}")
            return
        raise
    logger.info("抢票完成后退出程序。。。。。")
    hold_terminal_after_finish()
    exit_immediately_if_child_process()
