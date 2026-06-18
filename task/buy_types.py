from __future__ import annotations

import copy
import queue
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar


@dataclass
class BuyStreamState:
    stage: str = "初始化"
    countdown: str = "-"
    countdown_seconds: int | None = None
    current_proxy: str = "未初始化"
    proxy_pool: str = ""
    cooldown_remaining: int | None = None
    attempt_current: int | None = None
    attempt_total: int | None = None
    payment_qr_url: str | None = None
    status: str = "running"
    last_message: str = ""


@dataclass
class BuyStreamEvent:
    kind: str
    message: str | None
    state: BuyStreamState
    data: dict = field(default_factory=dict)


@dataclass(slots=True)
class BuyStreamUpdate:
    stage: str | None = None
    countdown: str | None = None
    countdown_seconds: int | None = None
    current_proxy: str | None = None
    proxy_pool: str | None = None
    cooldown_remaining: int | None = None
    attempt_current: int | None = None
    attempt_total: int | None = None
    payment_qr_url: str | None = None
    status: str | None = None

    def apply_to(self, state: BuyStreamState) -> None:
        if self.stage is not None:
            state.stage = self.stage
        if self.countdown is not None:
            state.countdown = self.countdown
        if self.countdown_seconds is not None:
            state.countdown_seconds = self.countdown_seconds
        if self.current_proxy is not None:
            state.current_proxy = self.current_proxy
        if self.proxy_pool is not None:
            state.proxy_pool = self.proxy_pool
        if self.cooldown_remaining is not None:
            state.cooldown_remaining = self.cooldown_remaining
        if self.attempt_current is not None:
            state.attempt_current = self.attempt_current
        if self.attempt_total is not None:
            state.attempt_total = self.attempt_total
        if self.payment_qr_url is not None:
            state.payment_qr_url = self.payment_qr_url
        if self.status is not None:
            state.status = self.status

    def to_dict(self) -> dict:
        data: dict = {}
        if self.stage is not None:
            data["stage"] = self.stage
        if self.countdown is not None:
            data["countdown"] = self.countdown
        if self.countdown_seconds is not None:
            data["countdown_seconds"] = self.countdown_seconds
        if self.current_proxy is not None:
            data["current_proxy"] = self.current_proxy
        if self.proxy_pool is not None:
            data["proxy_pool"] = self.proxy_pool
        if self.cooldown_remaining is not None:
            data["cooldown_remaining"] = self.cooldown_remaining
        if self.attempt_current is not None:
            data["attempt_current"] = self.attempt_current
        if self.attempt_total is not None:
            data["attempt_total"] = self.attempt_total
        if self.payment_qr_url is not None:
            data["payment_qr_url"] = self.payment_qr_url
        if self.status is not None:
            data["status"] = self.status
        return data


@dataclass
class RetryOutcome:
    err: int | None = None
    ret: dict | None = None
    exc: Exception | None = None

    def set_response(self, err: int, ret: dict) -> None:
        self.err = err
        self.ret = ret
        self.exc = None

    def set_exception(self, exc: Exception) -> None:
        self.exc = exc


@dataclass(frozen=True)
class CreateOrderTerminalRule:
    status: str
    message: str
    expose_payment_url: bool = False


T = TypeVar("T")


class LatestValueWorker(Generic[T]):
    def __init__(self, producer: Callable[..., Iterable[T]], *args, **kwargs):
        self._producer = producer
        self._args = args
        self._kwargs = kwargs
        self._queue: queue.Queue[T] = queue.Queue(maxsize=1)
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._latest_value: T | None = None
        self._error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run,
            name="latest-value-worker",
            daemon=True,
        )

    def start(self) -> "LatestValueWorker[T]":
        self._thread.start()
        return self

    def _publish(self, value: T) -> None:
        with self._lock:
            self._latest_value = copy.deepcopy(value)
        while True:
            try:
                self._queue.put_nowait(value)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    return

    def _run(self) -> None:
        try:
            for value in self._producer(*self._args, **self._kwargs):
                self._publish(value)
        except BaseException as exc:
            self._error = exc
        finally:
            self._done.set()

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def done(self) -> bool:
        return self._done.is_set()

    def latest_value(self) -> T | None:
        with self._lock:
            return copy.deepcopy(self._latest_value)

    def get_value(self, timeout: float | None = None) -> T | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def raise_if_failed(self) -> None:
        if self._error is not None:
            raise self._error

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)


class BuyStreamWorker(LatestValueWorker[BuyStreamEvent]):
    def __init__(
        self, producer: Callable[..., Iterable[BuyStreamEvent]], *args, **kwargs
    ):
        super().__init__(producer, *args, **kwargs)

    def latest_event(self) -> BuyStreamEvent | None:
        return self.latest_value()

    def get_event(self, timeout: float | None = None) -> BuyStreamEvent | None:
        return self.get_value(timeout=timeout)

    def iter_events(self, *, timeout: float = 0.1):
        while not self.done():
            event = self.get_event(timeout=timeout)
            if event is not None:
                yield event

        while True:
            event = self.get_event(timeout=0)
            if event is None:
                break
            yield event

        self.raise_if_failed()

    @staticmethod
    def start_buy_stream_worker(
        producer: Callable[..., Iterable[BuyStreamEvent]], *args, **kwargs
    ) -> "BuyStreamWorker":
        return BuyStreamWorker(producer, *args, **kwargs).start()
