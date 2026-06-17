import os
import sys
from loguru import logger


def loguru_config(
    log_dir: str,
    log_file_name: str,
    file_colorize: bool = False,
    enable_console: bool = True,
    file_level: str | None = None,
    console_level: str | None = None,
    retention_days: int | None = None,
) -> str:
    """
    配置 Loguru 日志系统。

    :param log_file_path: 日志文件的名称，会存储到 LOG_DIR 目录下"
    :param file_colorize: 是否为文件日志写入颜色控制符，默认关闭
    :param enable_console: 是否启用终端输出
    """
    logger.remove()

    resolved_file_level = (
        file_level or os.environ.get("BTB_LOG_LEVEL") or "DEBUG"
    ).upper()
    resolved_console_level = (
        console_level or os.environ.get("BTB_CONSOLE_LOG_LEVEL") or "INFO"
    ).upper()
    resolved_retention_days = retention_days
    if resolved_retention_days is None:
        try:
            resolved_retention_days = int(os.environ.get("BTB_LOG_RETENTION_DAYS", "7"))
        except ValueError:
            resolved_retention_days = 7

    logger.add(
        os.path.join(log_dir, log_file_name),
        level=resolved_file_level,
        encoding="utf-8",
        rotation="1 day",
        colorize=file_colorize,
        retention=f"{max(1, int(resolved_retention_days))} days",
        format="<green>[{time:YYYY-MM-DD:HH:mm:ss.SSS}]</green>|<level>{level}</level>|<level>{message}</level>",
    )

    if enable_console:
        logger.add(
            sys.stderr,
            level=resolved_console_level,
            colorize=True,
            format="<green>[{time:MM-DD:HH:mm:ss.SSS}]</green>|<level>{level}</level>|<level>{message}</level>",
        )
    return os.path.join(log_dir, log_file_name)
