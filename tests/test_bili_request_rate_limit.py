import httpx

from util.request.BiliRequest import BiliRequest
from util.request.exceptions import BiliRateLimitError


def test_request_raises_rate_limit_error(monkeypatch):
    request = BiliRequest(cookies=[])
    response = httpx.Response(
        429,
        request=httpx.Request(
            "POST", "https://show.bilibili.com/api/ticket/order/createV2"
        ),
    )
    monkeypatch.setattr(request, "_h2_send", lambda *args, **kwargs: response)

    try:
        request.post("https://show.bilibili.com/api/ticket/order/createV2", data={})
    except BiliRateLimitError as exc:
        assert "请求被限流(HTTP 429)" in str(exc)
        assert exc.response is response
    else:
        raise AssertionError("expected BiliRateLimitError")
