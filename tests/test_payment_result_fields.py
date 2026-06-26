from __future__ import annotations

from types import SimpleNamespace

from interface.execution import _collect_payment_fields_from_event
from task.buy_helpers import build_payment_result
from task.buy_types import BuyStreamEvent, BuyStreamState


class _DummyRequest:
    def get(self, url):
        assert "getPayParam?order_id=12345" in url
        return SimpleNamespace(
            json=lambda: {
                "errno": 0,
                "data": {"code_url": "weixin://wxpay/bizpayurl?pr=example"},
            }
        )


def test_build_payment_result_contains_order_and_code_urls():
    result = build_payment_result(_DummyRequest(), 12345)

    assert result["order_id"] == 12345
    assert result["order_detail_url"].endswith(
        "/platform/orderDetail.html?order_id=12345"
    )
    assert result["payment_code_url"] == "weixin://wxpay/bizpayurl?pr=example"
    assert result["payment_qr_url"] == result["order_detail_url"]


def test_collect_payment_fields_from_event_reads_new_fields():
    event = BuyStreamEvent(
        kind="payment_qr",
        message="PAYMENT_CODE_URL=weixin://wxpay/bizpayurl?pr=example",
        state=BuyStreamState(
            payment_qr_url="https://show.bilibili.com/platform/orderDetail.html?order_id=12345",
            order_id=12345,
            order_detail_url="https://show.bilibili.com/platform/orderDetail.html?order_id=12345",
            payment_code_url="weixin://wxpay/bizpayurl?pr=example",
        ),
    )

    fields = _collect_payment_fields_from_event(event)

    assert fields == {
        "payment_qr_url": "https://show.bilibili.com/platform/orderDetail.html?order_id=12345",
        "order_id": 12345,
        "order_detail_url": "https://show.bilibili.com/platform/orderDetail.html?order_id=12345",
        "payment_code_url": "weixin://wxpay/bizpayurl?pr=example",
    }
