import threading
from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from task.buy import buy_stream

cancel_event = threading.Event()


class BuyRequest(BaseModel):
    force: bool
    train_info: str
    time_start: str
    interval: int
    mode: int
    total_attempts: int
    audio_path: str | None
    pushplusToken: str | None
    serverchanKey: str | None


current_task_thread: threading.Thread | None = None
cancel_event = threading.Event()
task_lock = threading.Lock()


def create_worker_app(app: FastAPI, args):
    @app.post("/buy")
    async def buy_ticket(data: BuyRequest):
        global current_task_thread

        with task_lock:
            if current_task_thread and current_task_thread.is_alive():
                if data.force:
                    cancel_event.set()
                    logger.info("force=True，正在取消当前任务...")
                    current_task_thread.join()
                    logger.info("旧任务已终止，准备启动新任务")
                else:
                    raise HTTPException(status_code=409, detail="抢票任务正在进行中")

            cancel_event.clear()

            def stream():
                for msg in buy_stream(
                    tickets_info_str=data.train_info,
                    time_start=data.time_start,
                    interval=data.interval,
                    mode=data.mode,
                    total_attempts=data.total_attempts,
                    audio_path=data.audio_path,
                    pushplusToken=data.pushplusToken,
                    serverchanKey=data.serverchanKey,
                    https_proxys=args.https_proxys,
                ):
                    if cancel_event.is_set():
                        logger.info("任务被取消")
                        break
                    logger.info(msg)

            current_task_thread = threading.Thread(target=stream)
            current_task_thread.start()

            logger.info("新任务已启动")
            return {"status": "started"}


def stop_now_work():
    if current_task_thread and current_task_thread.is_alive():
        cancel_event.set()
        current_task_thread.join()
