from argparse import Namespace
import os
import re
import sys


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

    def hold_terminal_after_interrupt():
        try:
            if os.name == "nt":
                import msvcrt

                print("已停止当前抢票流程。按任意键关闭此窗口...", flush=True)
                msvcrt.getwch()
                return

            if not sys.stdin or not sys.stdin.isatty():
                return
            input("已停止当前抢票流程。按回车关闭此窗口...")
        except (EOFError, KeyboardInterrupt):
            pass

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
            )
    except KeyboardInterrupt:
        logger.warning("收到 Ctrl+C，已停止当前抢票流程。")
        exit_immediately_if_child_process()
        hold_terminal_after_interrupt()
        return
    logger.info("抢票完成后退出程序。。。。。")
    exit_immediately_if_child_process()
