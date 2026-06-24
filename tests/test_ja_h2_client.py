from __future__ import annotations

import unittest
from typing import Any

import httpx

from h2client_loader import load_h2client_module


h2connection = load_h2client_module("h2connection")
ja_h2_client = load_h2client_module("ja_h2_client")

H2Response = h2connection.H2Response
RotatingIPJA3H2Client = ja_h2_client.RotatingIPJA3H2Client
SourceAddress = ja_h2_client.SourceAddress


class FakeH2Connection:
    fail_healthcheck_sources: set[str] = set()
    fail_request_sources: set[str] = set()
    instances: list["FakeH2Connection"] = []

    def __init__(
        self,
        remote_host: str,
        source_ip: str | None,
        *,
        port: int = 443,
        sni: str | None = None,
        family: str = "auto",
        timeout: float = 10.0,
        assert_ja: bool = False,
    ) -> None:
        self.remote_host = remote_host
        self.source_ip = source_ip or ""
        self.port = port
        self.sni = sni
        self.family = family
        self.timeout = timeout
        self.assert_ja = assert_ja
        self.calls: list[tuple[str, str, Any, Any]] = []
        self.closed = False
        self.instances.append(self)

    def get(self, url: str, headers=None) -> H2Response:
        self.calls.append(("GET", url, headers, None))
        if url == "https://show.bilibili.com/":
            if self.source_ip in self.fail_healthcheck_sources:
                raise OSError("healthcheck failed")
        elif self.source_ip in self.fail_request_sources:
            raise OSError("request failed")
        return H2Response(
            status=200,
            headers=[(":status", "200"), ("content-type", "text/plain")],
            body=self.source_ip.encode("ascii"),
            stream_id=len(self.calls),
        )

    def post(self, url: str, headers=None, content=None) -> H2Response:
        self.calls.append(("POST", url, headers, content))
        if self.source_ip in self.fail_request_sources:
            raise OSError("request failed")
        return H2Response(
            status=200,
            headers=[(":status", "200"), ("content-type", "text/plain")],
            body=content or b"",
            stream_id=len(self.calls),
        )

    def close(self) -> None:
        self.closed = True


class FakeFallbackClient:
    instances: list["FakeFallbackClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.headers = httpx.Headers(kwargs.get("headers") or {})
        self.cookies = httpx.Cookies(kwargs.get("cookies"))
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.closed = False
        self.instances.append(self)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(("GET", url, kwargs))
        return httpx.Response(
            200,
            text="fallback-get",
            request=httpx.Request("GET", url),
        )

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(("POST", url, kwargs))
        return httpx.Response(
            200,
            text="fallback-post",
            request=httpx.Request("POST", url),
        )

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append(("HEAD", url, kwargs))
        return httpx.Response(
            200,
            request=httpx.Request("HEAD", url),
        )

    def close(self) -> None:
        self.closed = True


def first_slot(slots):
    return slots[0]


class RotatingIPJA3H2ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeH2Connection.fail_healthcheck_sources = set()
        FakeH2Connection.fail_request_sources = set()
        FakeH2Connection.instances = []
        FakeFallbackClient.instances = []

    def test_constructor_keeps_only_healthchecked_sources(self) -> None:
        FakeH2Connection.fail_healthcheck_sources = {"192.0.2.2"}

        client = RotatingIPJA3H2Client(
            headers={"user-agent": "ua"},
            source_ip_provider=lambda: [
                SourceAddress("192.0.2.1", "ipv4", "WLAN"),
                SourceAddress("192.0.2.2", "ipv4", "Ethernet"),
            ],
            connection_factory=FakeH2Connection,
            slot_chooser=first_slot,
        )

        self.assertEqual(client.available_source_ips, ["192.0.2.1"])
        self.assertEqual(len(FakeH2Connection.instances), 2)
        self.assertTrue(FakeH2Connection.instances[1].closed)

        client.close()

    def test_get_uses_headers_cookies_and_params(self) -> None:
        client = RotatingIPJA3H2Client(
            headers={"user-agent": "ua"},
            source_ip_provider=lambda: [SourceAddress("192.0.2.1", "ipv4", "WLAN")],
            connection_factory=FakeH2Connection,
            slot_chooser=first_slot,
        )
        client.cookies.set("SESSDATA", "abc", domain=".bilibili.com")

        response = client.get(
            "https://show.bilibili.com/api/ticket",
            params={"project_id": "1"},
        )

        self.assertEqual(response.status_code, 200)
        connection = FakeH2Connection.instances[0]
        method, url, headers, _ = connection.calls[-1]
        self.assertEqual(method, "GET")
        self.assertEqual(url, "https://show.bilibili.com/api/ticket?project_id=1")
        self.assertEqual(headers["user-agent"], "ua")
        self.assertIn("SESSDATA=abc", headers["cookie"])

        client.close()

    def test_post_json_sets_body_and_content_type(self) -> None:
        client = RotatingIPJA3H2Client(
            source_ip_provider=lambda: [SourceAddress("192.0.2.1", "ipv4", "WLAN")],
            connection_factory=FakeH2Connection,
            slot_chooser=first_slot,
        )

        response = client.post(
            "https://show.bilibili.com/api/ticket/order/createV2",
            json={"project_id": 1},
        )

        self.assertEqual(response.text, '{"project_id":1}')
        _, _, headers, content = FakeH2Connection.instances[0].calls[-1]
        self.assertEqual(headers["content-type"], "application/json")
        self.assertNotEqual(headers.get("content-length"), "0")
        self.assertEqual(content, b'{"project_id":1}')

        client.close()

    def test_request_failure_switches_to_next_source_ip(self) -> None:
        FakeH2Connection.fail_request_sources = {"192.0.2.1"}
        client = RotatingIPJA3H2Client(
            source_ip_provider=lambda: [
                SourceAddress("192.0.2.1", "ipv4", "WLAN"),
                SourceAddress("192.0.2.2", "ipv4", "Ethernet"),
            ],
            connection_factory=FakeH2Connection,
            slot_chooser=first_slot,
        )

        response = client.get("https://show.bilibili.com/api/ticket")

        self.assertEqual(response.text, "192.0.2.2")
        self.assertTrue(FakeH2Connection.instances[0].closed)

        client.close()

    def test_non_show_get_delegates_to_fallback_httpx_client(self) -> None:
        client = RotatingIPJA3H2Client(
            headers={"user-agent": "ua"},
            source_ip_provider=lambda: [SourceAddress("192.0.2.1", "ipv4", "WLAN")],
            connection_factory=FakeH2Connection,
            slot_chooser=first_slot,
            fallback_client_factory=FakeFallbackClient,
        )
        client.headers["x-client-header"] = "yes"
        client.cookies.set("SESSDATA", "abc", domain=".bilibili.com")

        response = client.get(
            "https://api.bilibili.com/x/web-interface/nav",
            params={"foo": "bar"},
            headers={"accept": "application/json"},
        )

        fallback = FakeFallbackClient.instances[0]
        self.assertEqual(response.text, "fallback-get")
        self.assertEqual(len(FakeH2Connection.instances[0].calls), 1)
        self.assertEqual(
            fallback.calls,
            [
                (
                    "GET",
                    "https://api.bilibili.com/x/web-interface/nav",
                    {
                        "params": {"foo": "bar"},
                        "headers": {"accept": "application/json"},
                    },
                )
            ],
        )
        self.assertEqual(fallback.headers["x-client-header"], "yes")
        self.assertEqual(fallback.cookies.get("SESSDATA"), "abc")

        client.close()

    def test_non_show_post_delegates_to_fallback_httpx_client(self) -> None:
        client = RotatingIPJA3H2Client(
            source_ip_provider=lambda: [SourceAddress("192.0.2.1", "ipv4", "WLAN")],
            connection_factory=FakeH2Connection,
            slot_chooser=first_slot,
            fallback_client_factory=FakeFallbackClient,
        )

        response = client.post(
            "https://api.bilibili.com/x/test",
            json={"ok": True},
            headers={"accept": "application/json"},
        )

        fallback = FakeFallbackClient.instances[0]
        self.assertEqual(response.text, "fallback-post")
        self.assertEqual(
            fallback.calls,
            [
                (
                    "POST",
                    "https://api.bilibili.com/x/test",
                    {
                        "data": None,
                        "json": {"ok": True},
                        "content": None,
                        "headers": {"accept": "application/json"},
                    },
                )
            ],
        )

        client.close()


if __name__ == "__main__":
    unittest.main()
