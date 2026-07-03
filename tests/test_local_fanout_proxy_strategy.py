from typing import Any

import httpx

from app_cmd.config.BuyConfig import BuyConfig
from interface.config import build_runtime_options
from tab.go import _build_task_proxy_list
from util.request.BiliRequest import AbstractH2Client, BiliRequest
from util.h2client.h2connection import H2Response
from util.h2client.ja_h2_client import ProxyPoolCreateV2FanoutJA3H2Client


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


class FakeH2Connection:
    instances: list["FakeH2Connection"] = []
    post_bodies_by_proxy: dict[str, list[bytes]] = {}

    def __init__(
        self,
        remote_host: str,
        source_ip: str | None,
        *,
        port: int = 443,
        sni: str | None = None,
        family: str = "auto",
        timeout: float = 10.0,
        proxy_url: str | None = None,
        assert_ja: bool = False,
    ) -> None:
        self.remote_host = remote_host
        self.source_ip = source_ip
        self.proxy_url = proxy_url
        self.calls: list[tuple[str, str]] = []
        self.closed = False
        self.instances.append(self)

    def get(self, url: str, headers=None) -> H2Response:
        self.calls.append(("GET", url))
        return H2Response(
            status=200,
            headers=[(":status", "200")],
            body=b"ok",
            stream_id=len(self.calls),
        )

    def post(self, url: str, headers=None, content=None) -> H2Response:
        self.calls.append(("POST", url))
        bodies = self.post_bodies_by_proxy.get(self.proxy_url or "", [])
        body = bodies.pop(0) if bodies else b'{"errno":0}'
        return H2Response(
            status=200,
            headers=[(":status", "200")],
            body=body,
            stream_id=len(self.calls),
        )

    def close(self) -> None:
        self.closed = True


def test_task_proxy_list_includes_direct_when_enabled():
    assert _build_task_proxy_list(
        "http://127.0.0.1:18080,http://127.0.0.1:28080",
        include_direct=True,
    ) == [
        "none",
        "http://127.0.0.1:18080",
        "http://127.0.0.1:28080",
    ]


def test_task_proxy_list_excludes_direct_when_disabled():
    assert _build_task_proxy_list(
        "none,http://127.0.0.1:18080,direct,http://127.0.0.1:28080",
        include_direct=False,
    ) == [
        "http://127.0.0.1:18080",
        "http://127.0.0.1:28080",
    ]


def test_task_proxy_list_can_require_configured_proxy():
    assert _build_task_proxy_list("", include_direct=False) == []


def test_runtime_strategy_flows_into_buy_config():
    runtime = build_runtime_options(
        create_request_proxy_strategy="local_fanout",
    )

    config = BuyConfig.from_runtime_options("{}", runtime)

    assert config.create_request_proxy_strategy == "local_fanout"
    assert "--create-request-proxy-strategy" in config.to_cli_args()


def test_h2_client_constructor_uses_abstract_client_interface():
    FakeH2Client.instances = []
    request = BiliRequest(
        cookies=[{"name": "SESSDATA", "value": "abc"}],
        h2_client_type=FakeH2Client,
        h2_client_options={"proxy_pool": ["http://127.0.0.1:8080"]},
    )
    url = "https://show.bilibili.com/api/ticket/order/createV2"

    request.prewarm_h2_connection(url)
    request._h2_send("post", url, data={"project_id": 1}, isJson=True)
    request._h2_send("get", url, data={"project_id": 1})

    client = FakeH2Client.instances[0]
    assert client.kwargs["http2"] is True
    assert client.kwargs["proxy_pool"] == ["http://127.0.0.1:8080"]
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


def test_replace_proxy_pool_updates_h2_client_options():
    FakeH2Client.instances = []
    request = BiliRequest(
        cookies=[{"name": "SESSDATA", "value": "abc"}],
        proxy="http://127.0.0.1:18080",
        h2_client_type=FakeH2Client,
        h2_client_options={"proxy_pool": ["http://127.0.0.1:18080"]},
    )
    url = "https://show.bilibili.com/api/ticket/order/createV2"

    request._h2_send("post", url, data={"project_id": 1}, isJson=True)
    first_client = FakeH2Client.instances[0]

    request.replace_proxy_pool("http://127.0.0.1:28080,http://127.0.0.1:38080")
    request._h2_send("post", url, data={"project_id": 1}, isJson=True)

    assert first_client.closed is True
    assert FakeH2Client.instances[1].kwargs["proxy_pool"] == [
        "http://127.0.0.1:28080",
        "http://127.0.0.1:38080",
    ]


def test_proxy_pool_fanout_builds_one_create_connection_per_proxy():
    FakeH2Connection.instances = []
    FakeH2Connection.post_bodies_by_proxy = {}
    client = ProxyPoolCreateV2FanoutJA3H2Client(
        proxy_pool=[
            "http://127.0.0.1:18080",
            "socks5://127.0.0.1:19090",
        ],
        connection_factory=FakeH2Connection,
        connections_per_source_ip=1,
    )

    response = client.post(
        "https://show.bilibili.com/api/ticket/order/createV2",
        json={"project_id": 1},
    )

    assert response.status_code == 200
    business_connections = [
        instance
        for instance in FakeH2Connection.instances
        if instance.calls
        and instance.calls[-1][1]
        == "https://show.bilibili.com/api/ticket/order/createV2"
    ]
    assert sorted(instance.proxy_url for instance in business_connections) == [
        "http://127.0.0.1:18080",
        "socks5://127.0.0.1:19090",
    ]


def test_proxy_pool_fanout_repeats_until_one_proxy_succeeds():
    FakeH2Connection.instances = []
    FakeH2Connection.post_bodies_by_proxy = {
        "http://127.0.0.1:18080": [b'{"errno":900001}', b'{"errno":900001}'],
        "http://127.0.0.1:28080": [b'{"errno":900001}', b'{"errno":0}'],
    }
    client = ProxyPoolCreateV2FanoutJA3H2Client(
        proxy_pool=[
            "http://127.0.0.1:18080",
            "http://127.0.0.1:28080",
        ],
        connection_factory=FakeH2Connection,
        connections_per_source_ip=1,
    )

    response = client.post(
        "https://show.bilibili.com/api/ticket/order/createV2",
        json={"project_id": 1},
    )

    assert response.json()["errno"] == 0
    post_count = sum(
        1
        for instance in FakeH2Connection.instances
        for call in instance.calls
        if call[0] == "POST"
    )
    assert post_count >= 4
