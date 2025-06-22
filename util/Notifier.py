from abc import ABC, abstractmethod
import threading
import loguru
import time

class NotifierBase(ABC):
    """
    循环通知发送基类，使用请实现send_message方法
    """
    def __init__(
        self,
        title:str,
        content:str,
        interval_seconds=10,
        duration_minutes=10 #B站订单保存上限
    ):
        super().__init__()
        self.title = title
        self.content = content
        self.interval_seconds = interval_seconds
        self.duration_minutes = duration_minutes
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=False)

    def run(self):
        """线程运行函数，实现间隔发送通知"""
        start_time = time.time()
        end_time = start_time + (self.duration_minutes * 60)
        count = 0

        while time.time() < end_time and not self.stop_event.is_set():
            try:
                # 构建消息内容，包含剩余时间
                remaining_minutes = int((end_time - time.time()) / 60)
                remaining_seconds = int((end_time - time.time()) % 60)
                message = f"{self.content} [#{count}, 剩余 {remaining_minutes}分{remaining_seconds}秒]"

                # 使用send_message方法发送
                self.send_message(self.title, message)
                # 确认发送成功后停止发送
                break 

            except Exception as e:
                loguru.logger.error(f"通知发送失败: {e}")
                time.sleep(self.interval_seconds)  # 发生错误时等待重试

        loguru.logger.info(f"通知发送成功")
    
    def start(self):
        if not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self.run, daemon=False)
            self.thread.start()
    
    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)

    @abstractmethod
    def send_message(self, title, message):
        """用于发送消息，子类必须实现此方法发送推送消息"""
        pass

class NotifierManager():
    def __init__(self):
        self.notifier_dict:dict[str,NotifierBase] = {}

    def regiseter_notifier(self, name:str, notifer:NotifierBase):
        if name in self.notifier_dict:
            loguru.logger.error(f"推送器添加失败: 已存在名为{name}的推送器")
        else:
            self.notifier_dict[name] = notifer
            loguru.logger.info(f"成功添加推送器: {name}")
    
    def remove_notifier(self, name:str):
        if name in self.notifier_dict:
            loguru.logger.error(f"推送器删除失败: 不存在名为{name}的推送器")
        else:
            self.notifier_dict.pop(name)
            loguru.logger.info(f"成功删除推送器: {name}")
    
    def start_all(self):
        for notifer in self.notifier_dict.values():
            notifer.start()

    def stop_all(self):
        for notifer in self.notifier_dict.values():
            notifer.stop()

    def start_notifer(self, name: str):
        notifer = self.notifier_dict.get(name)
        if notifer:
            notifer.start()
        else:
            loguru.logger.error(f"推送器启动失败: 不存在名为{name}的推送器")

    def stop_notifer(self, name: str):
        notifer = self.notifier_dict.get(name)
        if notifer:
            notifer.stop()
        else:
            loguru.logger.error(f"推送器停止失败: 不存在名为{name}的推送器")
    
    def list_notifers(self):
        return list(self.notifier_dict.keys())