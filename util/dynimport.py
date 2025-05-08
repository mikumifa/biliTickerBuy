import importlib
from typing import Any, Optional

from loguru import logger

global bili_ticket_gt_python
bili_ticket_gt_python: Optional[Any] = None
try:
    bili_ticket_gt_python = importlib.import_module("bili_ticket_gt_python")
except Exception as e:
    logger.error(f"本地验证码模块加载失败，错误信息：{e}")
    logger.info("正在使用不带有本地验证模块的模式启动")
