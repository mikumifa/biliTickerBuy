from __future__ import annotations

import os
import unittest
import urllib.parse

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


def get_capture_source_config():
    source_ip = os.environ.get("BTB_H2_CAPTURE_SOURCE_IP")
    family = os.environ.get("BTB_H2_CAPTURE_FAMILY")
    if source_ip:
        return source_ip, family or ("ipv6" if ":" in source_ip else "ipv4")
    return get_discovered_source_config()


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

    def test_build_post_headers_overrides_stale_content_length(self) -> None:
        headers = build_request_headers(
            "POST",
            "/api/ticket/order/prepare?project_id=1001653",
            remote_host="show.bilibili.com",
            headers=[
                ("host", "show.bilibili.com"),
                ("content-length", "0"),
                ("content-type", "application/json"),
            ],
            content_length=485,
        )

        self.assertNotIn(("host", "show.bilibili.com"), headers)
        self.assertNotIn(("content-length", "0"), headers)
        self.assertIn(("content-length", "485"), headers)

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

    @unittest.skipUnless(
        os.environ.get("BTB_H2_CAPTURE_ONCE") == "1",
        "manual packet-capture test; set BTB_H2_CAPTURE_ONCE=1 to run",
    )
    def test_manual_capture_single_request(self) -> None:
        url = os.environ.get("BTB_H2_CAPTURE_URL", "https://show.bilibili.com/api/ticket/order/createV2")
        method = os.environ.get("BTB_H2_CAPTURE_METHOD", "POST").upper()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("BTB_H2_CAPTURE_URL must be an absolute https:// URL")

        source_ip, family = get_capture_source_config()
        headers = {
            "accept": "*/*",
            "accept-encoding": "identity",
            "user-agent": os.environ.get("BTB_H2_CAPTURE_UA", "Mozilla/5.0"),
        }
        connection = H2Connection(
            parsed.hostname,
            source_ip,
            port=parsed.port or 443,
            family=family,
            assert_ja=True,
        )
        try:
            if method == "GET":
                response = connection.get(url, headers=headers)
            elif method == "POST":
                body = os.environ.get("BTB_H2_CAPTURE_BODY", "{}")
                headers["content-type"] = os.environ.get(
                    "BTB_H2_CAPTURE_CONTENT_TYPE",
                    "application/json",
                )
                response = connection.post(url, headers=headers, content=body)
            else:
                raise ValueError("BTB_H2_CAPTURE_METHOD must be GET or POST")

            print(
                "capture response "
                f"status={response.status} "
                f"body_len={len(response.body)} "
                f"source_ip={source_ip or 'auto'}"
                f"body_preview={response.body[:100]!r}",
            )
            self.assertIsNotNone(response.status)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
