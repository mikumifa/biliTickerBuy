from __future__ import annotations

import os
import statistics
import time
from dataclasses import dataclass

import ntplib
from loguru import logger

DEFAULT_NTP_SERVERS = (
    "ntp.aliyun.com",
    "ntp.tencent.com",
    "cn.ntp.org.cn",
    "time.cloudflare.com",
)


def current_time_ms(*, timeoffset: float = 0, base_ms: int | None = None) -> int:
    """
    Return a reference-time millisecond timestamp.

    timeoffset uses this project's historical sign convention:
    local wall time - reference/server wall time.
    """
    if base_ms is None:
        base_ms = int(time.time() * 1000)
    return int(base_ms - timeoffset * 1000)


@dataclass(frozen=True, slots=True)
class TimeSyncSample:
    source: str
    offset: float
    delay: float


class TimeUtil:
    # NTP服务器默认来自DEFAULT_NTP_SERVERS, 可根据实际情况修改
    def __init__(
        self,
        _ntp_server=None,
        *,
        ntp_servers: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.ntp_servers = list(
            ntp_servers
            if ntp_servers is not None
            else (DEFAULT_NTP_SERVERS if _ntp_server is None else (_ntp_server,))
        )
        self.ntp_server = self.ntp_servers[0]
        self.client = ntplib.NTPClient()
        self.timeoffset: float = 0
        self.time_source = "local"

    def compute_timeoffset(self) -> str:
        """
        返回的timeoffset单位为秒，语义为：本机时间 - 参考时间。
        """
        sample = self.compute_ntp_sample()
        if sample is None:
            logger.error("无法获取NTP时间")
            return "error"
        return format(sample.offset, ".5f")

    def compute_ntp_sample(
        self,
        *,
        attempts_per_server: int = 1,
        timeout: float = 1.2,
        primary_delay_threshold: float = 0.2,
    ) -> TimeSyncSample | None:
        """
        Compute local-reference offset from one or more NTP servers.
        """
        samples: list[TimeSyncSample] = []
        for server_index, server in enumerate(self.ntp_servers):
            for attempt in range(attempts_per_server):
                try:
                    response = self.client.request(server, version=4, timeout=timeout)
                except Exception:
                    logger.warning(
                        f"{server} 第{attempt + 1}次获取NTP时间失败, 尝试重新获取"
                    )
                    if attempt + 1 < attempts_per_server:
                        time.sleep(0.2)
                    continue
                # ntplib offset is reference - local. Keep the existing project
                # convention: local - reference.
                samples.append(
                    TimeSyncSample(
                        source=server,
                        offset=-(response.offset),
                        delay=float(response.delay),
                    )
                )
                if (
                    server_index == 0
                    and response.delay <= primary_delay_threshold
                    and len(self.ntp_servers) > 1
                ):
                    return samples[0]
                break
        if not samples:
            return None
        low_delay_samples = sorted(samples, key=lambda item: item.delay)[
            : max(1, min(3, len(samples)))
        ]
        offset = statistics.median(item.offset for item in low_delay_samples)
        best = min(low_delay_samples, key=lambda item: item.delay)
        return TimeSyncSample(source=best.source, offset=offset, delay=best.delay)

    def set_timeoffset(self, _timeoffset: str) -> None:
        """
        传入的timeoffset单位为秒，语义为：本机时间 - 参考时间。
        """
        if _timeoffset == "error":
            self.timeoffset = 0
            self.time_source = "local"
            logger.warning("NTP时间同步失败, 使用本地时间")
        else:
            self.timeoffset = float(_timeoffset)
            self.time_source = "ntp"

    def get_timeoffset(self) -> float:
        """
        获取到的timeoffset单位为秒，语义为：本机时间 - 参考时间。
        """
        return self.timeoffset

    def sync_time(self) -> None:
        sample = self.compute_ntp_sample()
        if sample is None:
            self.set_timeoffset("error")
        else:
            self.timeoffset = sample.offset
            self.time_source = f"ntp:{sample.source}"
            logger.info(
                "NTP时间同步成功: source={}, offset(local-reference)={:.5f}s, "
                "delay={:.1f}ms",
                sample.source,
                sample.offset,
                sample.delay * 1000,
            )

    def now(self) -> float:
        """Return calibrated reference wall time in seconds."""
        return time.time() - self.timeoffset

    def countdown_now(self) -> float:
        """Return calibrated wall time in seconds for the countdown."""
        return self.now()

    def countdown_time_source(self) -> str:
        return self.time_source

    def current_time_ms(self) -> int:
        """Return calibrated reference wall time in milliseconds."""
        return current_time_ms(timeoffset=self.timeoffset)


def create_time_service(*, use_local_time: bool = False) -> TimeUtil:
    """Initialize a clock for one task after resolving its time source."""
    servers = os.environ.get("BTB_NTP_SERVERS")
    service = TimeUtil(ntp_servers=servers.split(",") if servers else None)
    if not use_local_time and os.environ.get("BTB_SKIP_INITIAL_TIME_SYNC") != "1":
        service.sync_time()
    return service
