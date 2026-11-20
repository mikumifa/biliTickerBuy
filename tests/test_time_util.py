from __future__ import annotations

import importlib

import pytest

from util.TimeUtil import TimeSyncSample, TimeUtil, current_time_ms


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


@pytest.mark.parametrize(
    ("sample", "expected_now", "expected_source"),
    [
        (TimeSyncSample("ntp.example", 0.25, 0.02), 100.25, "ntp:ntp.example"),
        (None, 100.5, "local"),
    ],
    ids=["ntp", "local-fallback"],
)
def test_countdown_uses_synced_time_source(
    monkeypatch, sample, expected_now, expected_source
):
    monkeypatch.setattr(time_util_module.time, "time", lambda: 100.5)
    service = TimeUtil()
    monkeypatch.setattr(service, "compute_ntp_sample", lambda: sample)
    service.sync_time()

    assert service.countdown_now() == pytest.approx(expected_now)
    assert service.countdown_time_source() == expected_source


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
