from argparse import Namespace
import threading
from weakref import proxy
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse

from task.buy import buy_stream

task_lock = threading.Lock()
cancel_event = threading.Event()


def create_worker_app(app: FastAPI, args: Namespace):
    @app.post("/buy")
    def buy_ticket(request: Request):
        if not task_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="抢票任务正在进行中")

        cancel_event.clear()

        def stream():
            try:
                for msg in buy_stream(
                    "G123 北京->上海",
                    "2025-05-14 08:00:00",
                    interval=1,
                    mode="fast",
                    total_attempts=9999,
                    timeoffset=0,
                    audio_path="a.mp3",
                    pushplusToken="xxx",
                    serverchanKey="yyy",
                    https_proxy=args.https_proxys,
                ):
                    if cancel_event.is_set():
                        yield "data: 任务已取消\n\n"
                        break
                    yield f"data: {msg}\n\n"
            finally:
                task_lock.release()

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/cancel")
    def cancel_task():
        if not task_lock.locked():
            return JSONResponse(content={"message": "没有任务在执行"}, status_code=200)
        cancel_event.set()
        return JSONResponse(content={"message": "取消请求已发出"}, status_code=200)
