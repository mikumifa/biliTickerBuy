import httpx

from util.request.BiliRequest import BiliRequest
from util.request.exceptions import BiliConnectionError


def test_request_retries_once_after_h2_local_protocol_error(monkeypatch):
    request = BiliRequest(cookies=[])
    response = httpx.Response(
        200,
        json={"msg": "", "data": {"ok": True}},
        request=httpx.Request(
            "POST", "https://show.bilibili.com/api/ticket/order/createV2"
        ),
    )
    calls = {"count": 0}
    invalidations = {"count": 0}

    def fake_h2_send(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.LocalProtocolError(
                "Invalid input ConnectionInputs.RECV_WINDOW_UPDATE in state ConnectionState.CLOSED"
            )
        return response

    def fake_invalidate():
        invalidations["count"] += 1

    monkeypatch.setattr(request, "_h2_send", fake_h2_send)
    monkeypatch.setattr(request, "_invalidate_h2_client", fake_invalidate)

    result = request.post(
        "https://show.bilibili.com/api/ticket/order/createV2",
        data={},
    )

    assert result is response
    assert calls["count"] == 2
    assert invalidations["count"] == 1


def test_request_raises_connection_error_after_second_h2_local_protocol_error(
    monkeypatch,
):
    request = BiliRequest(cookies=[])
    invalidations = {"count": 0}

    def fake_h2_send(*args, **kwargs):
        raise httpx.LocalProtocolError(
            "Invalid input ConnectionInputs.RECV_WINDOW_UPDATE in state ConnectionState.CLOSED"
        )

    def fake_invalidate():
        invalidations["count"] += 1

    monkeypatch.setattr(request, "_h2_send", fake_h2_send)
    monkeypatch.setattr(request, "_invalidate_h2_client", fake_invalidate)

    try:
        request.post("https://show.bilibili.com/api/ticket/order/createV2", data={})
    except BiliConnectionError as exc:
        assert "HTTP/2 连接已断开" in str(exc)
        assert isinstance(exc.cause, httpx.LocalProtocolError)
    else:
        raise AssertionError("expected BiliConnectionError")

    assert invalidations["count"] == 2


def test_request_raises_connection_error_after_second_read_timeout(monkeypatch):
    request = BiliRequest(cookies=[])
    invalidations = {"count": 0}

    def fake_h2_send(*args, **kwargs):
        raise httpx.ReadTimeout("The read operation timed out")

    def fake_invalidate():
        invalidations["count"] += 1

    monkeypatch.setattr(request, "_h2_send", fake_h2_send)
    monkeypatch.setattr(request, "_invalidate_h2_client", fake_invalidate)

    try:
        request.post(
            "https://show.bilibili.com/api/ticket/order/prepare?project_id=1", data={}
        )
    except BiliConnectionError as exc:
        assert "网络请求超时" in str(exc)
        assert isinstance(exc.cause, httpx.ReadTimeout)
    else:
        raise AssertionError("expected BiliConnectionError")

    assert invalidations["count"] == 2
