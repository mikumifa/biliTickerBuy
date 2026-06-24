from __future__ import annotations

import unittest

from h2client_loader import load_h2client_module


client_ja = load_h2client_module("client_ja")
h2connection = load_h2client_module("h2connection")
ja_h2_client = load_h2client_module("ja_h2_client")

TARGET_JA3 = client_ja.TARGET_JA3
TARGET_JA3_FULL = client_ja.TARGET_JA3_FULL
TARGET_JA4 = client_ja.TARGET_JA4
TARGET_JA4_R = client_ja.TARGET_JA4_R
H2Connection = h2connection.H2Connection
build_request_headers = h2connection.build_request_headers
verify_client_hello_ja = h2connection.verify_client_hello_ja
discover_interface_source_ips = ja_h2_client.discover_interface_source_ips


def get_discovered_source_config():
    sources = discover_interface_source_ips()
    if not sources:
        return None, "auto"
    source = sources[0]
    return source.ip, source.family


class H2ConnectionTests(unittest.TestCase):
    def test_default_client_hello_ja_matches_target(self) -> None:
        result = verify_client_hello_ja("show.bilibili.com")

        self.assertTrue(result.ok, result.mismatches)
        self.assertEqual(result.fingerprints.ja3_full, TARGET_JA3_FULL)
        self.assertEqual(result.fingerprints.ja3, TARGET_JA3)
        self.assertEqual(result.fingerprints.ja4, TARGET_JA4)
        self.assertEqual(result.fingerprints.ja4_r, TARGET_JA4_R)

    def test_build_get_headers_from_absolute_url(self) -> None:
        headers = build_request_headers(
            "GET",
            "https://show.bilibili.com/api/ticket/project/list?id=1",
            remote_host="show.bilibili.com",
            headers={
                "User-Agent": "ua",
                "Accept": "*/*",
                "Connection": "keep-alive",
            },
        )

        self.assertEqual(
            headers[:4],
            [
                (":method", "GET"),
                (":authority", "show.bilibili.com"),
                (":scheme", "https"),
                (":path", "/api/ticket/project/list?id=1"),
            ],
        )
        self.assertIn(("user-agent", "ua"), headers)
        self.assertIn(("accept", "*/*"), headers)
        self.assertNotIn(("connection", "keep-alive"), headers)

    def test_build_post_headers_adds_content_length(self) -> None:
        headers = build_request_headers(
            "POST",
            "/api/ticket/order/createV2",
            remote_host="show.bilibili.com",
            headers=[("content-type", "application/json")],
            content_length=2,
        )

        self.assertEqual(headers[0], (":method", "POST"))
        self.assertEqual(headers[3], (":path", "/api/ticket/order/createV2"))
        self.assertIn(("content-type", "application/json"), headers)
        self.assertIn(("content-length", "2"), headers)

    def test_connection_can_assert_ja_without_connecting(self) -> None:
        source_ip, family = get_discovered_source_config()
        connection = H2Connection(
            "show.bilibili.com",
            source_ip,
            family=family,
            assert_ja=True,
        )

        self.assertFalse(connection.connected)
        self.assertTrue(connection.verify_ja().ok)


if __name__ == "__main__":
    unittest.main()
