from __future__ import annotations

import importlib
import sys
import types


try:
    import qrcode  # noqa: F401
except ModuleNotFoundError:
    sys.modules["qrcode"] = types.ModuleType("qrcode")

buy_helpers = importlib.import_module("task.buy_helpers")


class _FakeTicketState:
    pass


class _FakeCreateState:
    def generate_create_ctoken(self):
        return "fake-ctoken"


class _FakeTimeService:
    def current_time_ms(self):
        return 1234567890


class _FakeCountdownTimeService:
    time_source = "fake"

    def __init__(self):
        self._now = 0.0

    def get_timeoffset(self):
        return 0.0

    def compute_bili_time_check(self, attempts=2, timeout=1.5):
        return None

    def countdown_time_source(self):
        return "fake"

    def countdown_now(self):
        self._now += 1.0
        return self._now


class _FakePerfCounter:
    def __init__(self):
        self._now = -1.0

    def __call__(self):
        self._now += 1.0
        return self._now


def test_prepare_create_request_uses_calibrated_timestamp(monkeypatch):
    monkeypatch.setattr(buy_helpers, "time_service", _FakeTimeService())
    monkeypatch.setattr(
        buy_helpers,
        "sim_ctoken_state",
        lambda before_state, now_ms: _FakeCreateState(),
    )

    url, payload = buy_helpers.prepare_create_request(
        {
            "project_id": 1,
            "screen_id": 2,
            "sku_id": 3,
            "count": 1,
            "order_type": 1,
            "buyer_info": [],
            "sale_start": "2026-01-01 12:00:00",
            "username": "user",
            "detail": "detail",
        },
        order_token="order-token",
        is_hot_project=True,
        request_result={"data": {}},
        ticket_state=_FakeTicketState(),
    )

    assert "/api/ticket/order/createV2?project_id=1" in url
    assert payload["timestamp"] == 1234567890
    assert payload["ctoken"] == "fake-ctoken"
    assert "sale_start" not in payload
    assert "username" not in payload
    assert "detail" not in payload


def test_wait_until_start_reports_warmup_failure_without_raising(monkeypatch):
    monkeypatch.setattr(buy_helpers, "time_service", _FakeCountdownTimeService())
    monkeypatch.setattr(buy_helpers.time, "perf_counter", _FakePerfCounter())
    monkeypatch.setattr(buy_helpers.time, "sleep", lambda seconds: None)

    def fail_warmup():
        raise RuntimeError("failed to fetch project detail")

    events = list(
        buy_helpers.wait_until_start(
            "1970-01-01 08:00:04",
            warmup=fail_warmup,
        )
    )

    messages = [event.get("message") for event in events]
    assert any(
        "failed to fetch project detail" in str(message) for message in messages
    )
