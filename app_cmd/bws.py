from __future__ import annotations

import os
import re
import sys
import threading
import time
import uuid

from app_cmd.config.BwsConfig import BwsConfig

TASK_COMPLETED_MARKER = "抢票完成后退出程序。。。。。"
TASK_STOPPED_MARKER = "BTB_TASK_STOPPED_BY_USER"


def _resolve_log_file_name() -> str:
    configured_name = os.environ.get("BTB_APP_LOG_NAME", "").strip()
    if configured_name:
        return re.sub(r"[^\w.\-]", "_", os.path.basename(configured_name))
    return f"bws-{uuid.uuid4()}.log"


def _hold_terminal(message: str) -> None:
    if os.environ.get("BTB_HOLD_TERMINAL", "") != "1":
        return
    try:
        if os.name == "nt":
            import msvcrt

            print(message, flush=True)
            msvcrt.getwch()
            return
        if sys.stdin and sys.stdin.isatty():
            input(message)
    except (EOFError, KeyboardInterrupt):
        pass


def _parent_pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        synchronize = 0x00100000
        still_active = 259

        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information | synchronize,
            False,
            pid,
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            ):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False
    return True


def _start_parent_watchdog(logger) -> None:
    raw_parent_pid = os.environ.get("BTB_PARENT_PID", "").strip()
    if not raw_parent_pid:
        return
    try:
        parent_pid = int(raw_parent_pid)
    except ValueError:
        return
    if parent_pid <= 0 or parent_pid == os.getpid():
        return

    def _watch_parent() -> None:
        while True:
            time.sleep(1.0)
            if _parent_pid_is_running(parent_pid):
                continue
            try:
                logger.warning("检测到主进程已退出，当前 BW 乐园预约子进程即将结束。")
            except Exception:
                pass
            os._exit(0)

    threading.Thread(
        target=_watch_parent,
        name="btb-bws-parent-watchdog",
        daemon=True,
    ).start()


def bws_cmd(args: BwsConfig) -> None:
    from loguru import logger

    from interface.bws import bws_reserve_stream
    from util import LOG_DIR
    from util.log.LogConfig import loguru_config

    loguru_config(LOG_DIR, _resolve_log_file_name(), enable_console=True)
    _start_parent_watchdog(logger)
    try:
        for message in bws_reserve_stream(args):
            logger.info(message)
    except KeyboardInterrupt:
        logger.warning(TASK_STOPPED_MARKER)
        logger.warning("收到 Ctrl+C，已停止 BW 乐园预约流程。")
        _hold_terminal("已停止当前 BW 乐园预约流程。按任意键关闭此窗口...")
    except Exception as exc:
        logger.exception(f"BW 乐园预约流程异常退出: {exc}")
        _hold_terminal(f"BW 乐园预约流程异常退出: {exc}\n按任意键关闭此窗口...")
        raise
    logger.info(TASK_COMPLETED_MARKER)
    _hold_terminal("BW 乐园预约流程已结束。按任意键关闭此窗口...")
