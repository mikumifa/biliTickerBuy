from __future__ import annotations

import uuid

from app_cmd.config.BwsConfig import BwsConfig


def bws_cmd(args: BwsConfig) -> None:
    from loguru import logger

    from interface.bws import bws_reserve_stream
    from util import LOG_DIR
    from util.log.LogConfig import loguru_config

    loguru_config(LOG_DIR, f"bws-{uuid.uuid4()}.log", enable_console=True)
    try:
        for message in bws_reserve_stream(args):
            logger.info(message)
    except KeyboardInterrupt:
        logger.warning("收到 Ctrl+C，已停止 BW 乐园预约流程。")
    except Exception as exc:
        logger.exception(f"BW 乐园预约流程异常退出: {exc}")
        raise
