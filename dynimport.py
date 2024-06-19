from loguru import logger
import importlib

global bili_ticket_gt_python

try:
	logger.info("尝试加载本地验证码模块")
	bili_ticket_gt_python = importlib.import_module("bili_ticket_gt_python")
	logger.info("加载成功")
except Exception as e:
	logger.error(f"本地验证码模块加载失败，错误信息：{e}")
	logger.info("正在使用不带有本地验证模块的模式启动")
	logger.warning("此模式下请勿使用本地验证码功能，否则会报错")
	bili_ticket_gt_python = None