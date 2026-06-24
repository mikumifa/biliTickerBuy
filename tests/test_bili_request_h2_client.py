from typing import Any

import httpx

from util.request.BiliRequest import AbstractH2Client, BiliRequest


class FakeCookies:
    def __init__(self) -> None:
        self.values: list[tuple[str, str, str]] = []

    def set(
        self,
        name: str,
        value: str,
        domain: str = "",
        path: str = "/",
    ) -> None:
        self.values.append((name, value, domain))


class FakeH2Client(AbstractH2Client):
    instances: list["FakeH2Client"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self._headers = dict(kwargs.get("headers", {}))
        self._cookies = FakeCookies()
        self.calls: list[tuple] = []
        self.closed = False
        self.instances.append(self)

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @property
    def cookies(self) -> FakeCookies:
        return self._cookies

    def head(self, url: str) -> httpx.Response:
        self.calls.append(("head", url))
        return httpx.Response(200, request=httpx.Request("HEAD", url))

    def get(self, url: str, *, params: Any = None) -> httpx.Response:
        self.calls.append(("get", url, params))
        return httpx.Response(
            200,
            json={"msg": ""},
            request=httpx.Request("GET", url),
        )

    def post(
        self,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
    ) -> httpx.Response:
        self.calls.append(("post", url, data, json))
        return httpx.Response(
            200,
            json={"msg": ""},
            request=httpx.Request("POST", url),
        )

    def close(self) -> None:
        self.closed = True


def test_h2_client_constructor_uses_abstract_client_interface():
    FakeH2Client.instances = []
    request = BiliRequest(
        cookies=[{"name": "SESSDATA", "value": "abc"}],
        h2_client_type=FakeH2Client,
    )
    url = "https://show.bilibili.com/api/ticket/order/createV2"

    request.prewarm_h2_connection(url)
    request._h2_send("post", url, data={"project_id": 1}, isJson=True)
    request._h2_send("get", url, data={"project_id": 1})

    client = FakeH2Client.instances[0]
    assert client.kwargs["http2"] is True
    assert client.headers["user-agent"] == request.get_user_agent()
    assert client.cookies.values == [
        ("SESSDATA", "abc", ".bilibili.com"),
        ("SESSDATA", "abc", ".bilibili.com"),
        ("SESSDATA", "abc", ".bilibili.com"),
    ]
    assert client.calls == [
        ("head", url),
        ("post", url, None, {"project_id": 1}),
        ("get", url, {"project_id": 1}),
    ]

    request._invalidate_h2_client()

    assert client.closed is True
