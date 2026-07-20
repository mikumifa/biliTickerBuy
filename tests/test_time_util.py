from __future__ import annotations

import datetime
import importlib

import pytest

from util.TimeUtil import BiliTimeCheck, TimeUtil, current_time_ms


time_util_module = importlib.import_module("util.TimeUtil")


def test_current_time_ms_applies_local_minus_reference_offset():
    assert current_time_ms(timeoffset=0.25, base_ms=1_000) == 750
    assert current_time_ms(timeoffset=-0.25, base_ms=1_000) == 1_250


def test_time_service_now_uses_calibrated_reference_time(monkeypatch):
    monkeypatch.setattr(time_util_module.time, "time", lambda: 100.5)
    service = TimeUtil()
    service.set_timeoffset("0.25000")

    assert service.now() == pytest.approx(100.25)
    assert service.current_time_ms() == 100_250


def test_countdown_now_prefers_bili_date_check(monkeypatch):
    monkeypatch.setattr(time_util_module.time, "time", lambda: 100.5)
    service = TimeUtil()
    service.set_timeoffset("0.25000")
    service.last_bili_check = BiliTimeCheck(
        offset_center=0.75,
        delay=0.1,
        date_header="Sun, 28 Jun 2026 09:43:08 GMT",
        status_code=412,
        source_url="https://show.bilibili.com/api/ticket/project/listV2",
    )

    assert service.countdown_now() == pytest.approx(99.75)
    assert service.countdown_time_source() == "bili-date"


def test_compute_ntp_sample_uses_low_delay_median():
    class Response:
        def __init__(self, offset, delay):
            self.offset = offset
            self.delay = delay

    class Client:
        def __init__(self):
            self.responses = {
                "slow.example": Response(offset=-0.8, delay=0.5),
                "fast-a.example": Response(offset=-0.2, delay=0.02),
                "fast-b.example": Response(offset=-0.24, delay=0.03),
            }

        def request(self, server, version, timeout):
            return self.responses[server]

    service = TimeUtil(ntp_servers=("slow.example", "fast-a.example", "fast-b.example"))
    service.client = Client()

    sample = service.compute_ntp_sample(attempts_per_server=1)

    assert sample is not None
    assert sample.source == "fast-a.example"
    assert sample.offset == pytest.approx(0.24)


def test_compute_ntp_sample_returns_fast_primary_without_backup_calls():
    class Response:
        offset = -0.2
        delay = 0.02

    class Client:
        def __init__(self):
            self.calls = []

        def request(self, server, version, timeout):
            self.calls.append(server)
            return Response()

    service = TimeUtil(ntp_servers=("primary.example", "backup.example"))
    client = Client()
    service.client = client

    sample = service.compute_ntp_sample()

    assert sample is not None
    assert sample.source == "primary.example"
    assert sample.offset == pytest.approx(0.2)
    assert client.calls == ["primary.example"]


def test_compute_bili_time_check_parses_http_date(monkeypatch):
    class Response:
        status_code = 412
        headers = {
            "Date": "Sun, 28 Jun 2026 09:43:08 GMT",
        }

    ticks = iter([1782639788.0, 1782639788.1])
    monkeypatch.setattr(time_util_module.time, "time", lambda: next(ticks))
    monkeypatch.setattr(time_util_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        time_util_module.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )
    service = TimeUtil()

    check = service.compute_bili_time_check(attempts=1)

    assert check is not None
    server_second = datetime.datetime(
        2026, 6, 28, 9, 43, 8, tzinfo=datetime.timezone.utc
    ).timestamp()
    assert check.offset_center == pytest.approx(
        ((1782639788.0 + 1782639788.1) / 2) - (server_second + 0.5)
    )
    assert check.uncertainty_seconds == pytest.approx(0.55)
