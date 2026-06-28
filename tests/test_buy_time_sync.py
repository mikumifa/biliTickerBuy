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
