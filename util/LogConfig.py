import os
import sys
from loguru import logger


def loguru_config(
    log_dir: str,
    log_file_name: str,
    file_colorize=True,
    enable_console: bool = True,
) -> str:
    """
    配置 Loguru 日志系统。

    :param log_file_path: 日志文件的名称，会存储到 LOG_DIR 目录下"
    :param enable_console: 是否启用终端输出
    """
    logger.remove()

    logger.add(
        os.path.join(log_dir, log_file_name),
        level="DEBUG",  # DEBUG
        encoding="utf-8",
        rotation="1 day",
        colorize=file_colorize,
        retention="7 days",
        format="<green>[{time:YYYY-MM-DD:HH:mm:ss.SSS}]</green>|<level>{level}</level>|<cyan>{name}</cyan>:<yellow>{line}</yellow>|<level>{message}</level>",
    )

    if enable_console:
        logger.add(
            sys.stderr,
            level="INFO",  # INFO
            colorize=True,
            format="<green>[{time:MM-DD:HH:mm:ss.SSS}]</green>|<level>{level}</level>|<level>{message}</level>",
        )
    return os.path.join(log_dir, log_file_name)
