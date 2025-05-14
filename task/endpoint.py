import os
import threading
import time
from gradio_client import Client
from loguru import logger

from util import GlobalStatusInstance


def start_heartbeat_thread(client: Client, self_url: str, to_url: str):
    """
    send task detail to Master

    """

    def report_heart(client: Client, self_url: str, to_url: str):
        cnt = 0
        try:
            res = client.predict(
                self_url,
                GlobalStatusInstance.nowTask,
                api_name="/report",
            )
            logger.debug(f"report_heart {self_url} -({res})-> {to_url}")
            cnt = 0
        except Exception as e:
            cnt += 1
            logger.error(f"report_heart error: {e}")
            if cnt > 5:
                logger.error("report_heart error too many times, exit")
                time.sleep(3)
                os._exit(1)

    def heartbeat_loop():
        while True:
            report_heart(client, self_url, to_url)
            time.sleep(1)

    t = threading.Thread(target=heartbeat_loop, daemon=True)
    t.start()
