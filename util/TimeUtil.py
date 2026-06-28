from __future__ import annotations

import email.utils
import statistics
import time
from dataclasses import dataclass

import ntplib
from loguru import logger
import requests

DEFAULT_NTP_SERVERS = (
    "ntp.aliyun.com",
    "ntp.tencent.com",
    "cn.ntp.org.cn",
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


@dataclass(frozen=True, slots=True)
class BiliTimeCheck:
    offset_center: float
    delay: float
    date_header: str
    status_code: int
    source_url: str

    @property
    def uncertainty_seconds(self) -> float:
        # RFC 7231 Date has second precision, plus half the measured RTT.
        return 0.5 + self.delay / 2


class TimeUtil:
    # NTP服务器默认为ntp.aliyun.com, 可根据实际情况修改
    def __init__(
        self,
        _ntp_server="ntp.aliyun.com",
        *,
        ntp_servers: list[str] | tuple[str, ...] | None = None,
        bili_time_url: str = "https://show.bilibili.com/api/ticket/project/listV2",
    ) -> None:
        self.ntp_servers = list(
            ntp_servers
            if ntp_servers is not None
            else (
                DEFAULT_NTP_SERVERS
                if _ntp_server == "ntp.aliyun.com"
                else (_ntp_server,)
            )
        )
        self.ntp_server = self.ntp_servers[0]
        self.bili_time_url = bili_time_url
        self.client = ntplib.NTPClient()
        self.timeoffset: float = 0
        self.time_source = "local"
        self.last_bili_check: BiliTimeCheck | None = None

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

    def compute_bili_time_check(
        self,
        *,
        url: str | None = None,
        attempts: int = 3,
        timeout: float = 3.0,
    ) -> BiliTimeCheck | None:
        """
        Estimate Bilibili Mall gateway time from the HTTP Date header.

        HTTP Date has second precision, so this is a coarse consistency check,
        not a replacement for NTP millisecond-level synchronization.
        """
        source_url = url or self.bili_time_url
        checks: list[BiliTimeCheck] = []
        for attempt in range(attempts):
            try:
                t0 = time.time()
                response = requests.get(
                    source_url,
                    headers={
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    },
                    timeout=timeout,
                    allow_redirects=False,
                )
                t1 = time.time()
            except Exception as exc:
                logger.warning(f"第{attempt + 1}次获取会员购时间失败: {exc}")
                continue
            date_header = response.headers.get("Date")
            if not date_header:
                logger.warning("会员购响应缺少 Date 头，无法校验时间")
                continue
            try:
                server_second = email.utils.parsedate_to_datetime(
                    date_header
                ).timestamp()
            except Exception as exc:
                logger.warning(f"无法解析会员购 Date 头: {date_header!r}, {exc}")
                continue
            local_midpoint = (t0 + t1) / 2
            offset_center = local_midpoint - (server_second + 0.5)
            checks.append(
                BiliTimeCheck(
                    offset_center=offset_center,
                    delay=t1 - t0,
                    date_header=date_header,
                    status_code=response.status_code,
                    source_url=source_url,
                )
            )
            time.sleep(0.1)
        if not checks:
            return None
        self.last_bili_check = min(checks, key=lambda item: item.delay)
        return self.last_bili_check

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

    def sync_time(self, *, check_bili: bool = True) -> None:
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
        if check_bili:
            check = self.compute_bili_time_check()
            if check is None:
                return
            diff = check.offset_center - self.timeoffset
            logger.info(
                "会员购Date校验: offset(local-bili-center)={:.3f}s, "
                "与当前时间源差异约{:+.3f}s, 不确定度约±{:.3f}s, "
                "rtt={:.1f}ms, status={}",
                check.offset_center,
                diff,
                check.uncertainty_seconds,
                check.delay * 1000,
                check.status_code,
            )

    def now(self) -> float:
        """Return calibrated reference wall time in seconds."""
        return time.time() - self.timeoffset

    def current_time_ms(self) -> int:
        """Return calibrated reference wall time in milliseconds."""
        return current_time_ms(timeoffset=self.timeoffset)
