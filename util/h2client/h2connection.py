from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from h2.config import H2Configuration
from h2.connection import H2Connection as H2State
from h2.events import (
    ConnectionTerminated,
    DataReceived,
    ResponseReceived,
    StreamEnded,
    StreamReset,
    TrailersReceived,
)
from loguru import logger

try:
    from .client_ja import (
        ClientHelloProfile,
        Fingerprints,
        TARGET_JA3,
        TARGET_JA3_FULL,
        TARGET_JA4,
        TARGET_JA4_R,
        TLS13Connection,
        build_client_hello,
        connect_tcp,
        fingerprints_from_client_hello,
        open_tls13_connection,
    )
except ImportError:  # pragma: no cover - supports direct execution from this dir.
    from client_ja import (
        ClientHelloProfile,
        Fingerprints,
        TARGET_JA3,
        TARGET_JA3_FULL,
        TARGET_JA4,
        TARGET_JA4_R,
        TLS13Connection,
        build_client_hello,
        connect_tcp,
        fingerprints_from_client_hello,
        open_tls13_connection,
    )


HeaderItems = Mapping[str, str] | Sequence[tuple[str, str]]
AddressFamily = Literal["auto", "ipv4", "ipv6"]

_CONNECTION_SPECIFIC_HEADERS = {
    "connection",
    "host",
    "keep-alive",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass(frozen=True)
class H2Response:
    status: int | None
    headers: list[tuple[str, str]]
    body: bytes
    stream_id: int

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)


@dataclass(frozen=True)
class RequestTarget:
    scheme: str
    authority: str
    path: str


@dataclass(frozen=True)
class JAMatch:
    fingerprints: Fingerprints
    expected: dict[str, str]
    padding_len: int

    @property
    def ok(self) -> bool:
        return (
            self.fingerprints.ja3_full == self.expected["ja3_full"]
            and self.fingerprints.ja3 == self.expected["ja3"]
            and self.fingerprints.ja4 == self.expected["ja4"]
            and self.fingerprints.ja4_r == self.expected["ja4_r"]
        )

    @property
    def mismatches(self) -> dict[str, tuple[str, str]]:
        values = {
            "ja3_full": self.fingerprints.ja3_full,
            "ja3": self.fingerprints.ja3,
            "ja4": self.fingerprints.ja4,
            "ja4_r": self.fingerprints.ja4_r,
        }
        return {
            name: (actual, self.expected[name])
            for name, actual in values.items()
            if actual != self.expected[name]
        }


@dataclass(frozen=True)
class H2ConnectionConfig:
    remote_host: str
    source_ip: str | None
    port: int = 443
    sni: str | None = None
    family: AddressFamily = "auto"
    timeout: float = 10.0
    proxy_url: str | None = None
    profile: ClientHelloProfile = field(default_factory=ClientHelloProfile)

    @property
    def effective_sni(self) -> str:
        return self.sni or self.remote_host

    @property
    def authority(self) -> str:
        return format_authority(self.remote_host, self.port)


def format_authority(host: str, port: int) -> str:
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return host_part if port == 443 else f"{host_part}:{port}"


def verify_client_hello_ja(
    sni: str,
    *,
    profile: ClientHelloProfile | None = None,
    expected: Mapping[str, str] | None = None,
) -> JAMatch:
    profile = profile or ClientHelloProfile()
    built = build_client_hello(sni=sni, profile=profile)
    fingerprints = fingerprints_from_client_hello(built.record)
    expected_values = {
        "ja3_full": TARGET_JA3_FULL,
        "ja3": TARGET_JA3,
        "ja4": TARGET_JA4,
        "ja4_r": TARGET_JA4_R,
    }
    if expected:
        expected_values.update(expected)
    return JAMatch(
        fingerprints=fingerprints,
        expected=expected_values,
        padding_len=built.padding_len,
    )


def assert_client_hello_ja(
    sni: str,
    *,
    profile: ClientHelloProfile | None = None,
    expected: Mapping[str, str] | None = None,
) -> JAMatch:
    result = verify_client_hello_ja(
        sni,
        profile=profile,
        expected=expected,
    )
    if not result.ok:
        details = ", ".join(
            f"{name}: actual={actual!r}, expected={expected!r}"
            for name, (actual, expected) in result.mismatches.items()
        )
        raise RuntimeError(f"generated ClientHello JA mismatch: {details}")
    return result


def _coerce_body(content: bytes | str | None) -> bytes:
    if content is None:
        return b""
    if isinstance(content, bytes):
        return content
    return content.encode("utf-8")


def _body_for_log(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _header_value(headers: Sequence[tuple[str, str]], name: str) -> str:
    for header_name, value in headers:
        if header_name == name:
            return value
    return ""


def _normalize_header_items(headers: HeaderItems | None) -> list[tuple[str, str]]:
    if headers is None:
        return []
    items: Iterable[tuple[str, str]]
    if isinstance(headers, Mapping):
        items = headers.items()
    else:
        items = headers

    normalized: list[tuple[str, str]] = []
    for name, value in items:
        lower_name = str(name).lower()
        if lower_name.startswith(":"):
            continue
        if lower_name in _CONNECTION_SPECIFIC_HEADERS:
            continue
        normalized.append((lower_name, str(value)))
    return normalized


def _parse_request_target(
    url: str,
    *,
    remote_host: str,
    port: int,
) -> RequestTarget:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme:
        if parsed.scheme != "https":
            raise ValueError("only https:// URLs are supported")
        if not parsed.hostname:
            raise ValueError("URL must include a hostname")
        url_port = parsed.port or 443
        if parsed.hostname.lower() != remote_host.lower() or url_port != port:
            raise ValueError(
                "request URL host/port must match this maintained connection"
            )
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return RequestTarget(
            scheme="https",
            authority=format_authority(parsed.hostname, url_port),
            path=path,
        )

    path = url or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return RequestTarget(
        scheme="https",
        authority=format_authority(remote_host, port),
        path=path,
    )


def build_request_headers(
    method: str,
    url: str,
    *,
    remote_host: str,
    port: int = 443,
    headers: HeaderItems | None = None,
    content_length: int | None = None,
) -> list[tuple[str, str]]:
    method = method.upper()
    target = _parse_request_target(url, remote_host=remote_host, port=port)
    user_headers = _normalize_header_items(headers)

    request_headers = [
        (":method", method),
        (":authority", target.authority),
        (":scheme", target.scheme),
        (":path", target.path),
    ]
    if content_length is not None:
        user_headers = [
            (name, value)
            for name, value in user_headers
            if name != "content-length"
        ]
    request_headers.extend(user_headers)

    if content_length is not None:
        request_headers.append(("content-length", str(content_length)))

    return request_headers


class H2Connection:
    def __init__(
        self,
        remote_host: str,
        source_ip: str | None,
        *,
        port: int = 443,
        sni: str | None = None,
        family: AddressFamily = "auto",
        timeout: float = 10.0,
        proxy_url: str | None = None,
        profile: ClientHelloProfile | None = None,
        assert_ja: bool = False,
    ) -> None:
        self.config = H2ConnectionConfig(
            remote_host=remote_host,
            source_ip=source_ip,
            port=port,
            sni=sni,
            family=family,
            timeout=timeout,
            proxy_url=proxy_url,
            profile=profile or ClientHelloProfile(),
        )
        if assert_ja:
            assert_client_hello_ja(
                self.config.effective_sni,
                profile=self.config.profile,
            )
        self._sock = None
        self._tls: TLS13Connection | None = None
        self._h2: H2State | None = None

    @property
    def connected(self) -> bool:
        return self._tls is not None and self._h2 is not None

    @property
    def selected_alpn(self) -> str | None:
        return self._tls.selected_alpn if self._tls is not None else None

    @property
    def cipher_suite(self) -> str | None:
        return self._tls.cipher_suite if self._tls is not None else None

    def verify_ja(self) -> JAMatch:
        return verify_client_hello_ja(
            self.config.effective_sni,
            profile=self.config.profile,
        )

    def connect(self) -> None:
        if self.connected:
            return

        self._h2 = H2State(
            config=H2Configuration(
                client_side=True,
                header_encoding="utf-8",
                validate_outbound_headers=True,
                validate_inbound_headers=False,
            )
        )
        sock = None
        try:
            sock = connect_tcp(
                host=self.config.remote_host,
                port=self.config.port,
                family=self.config.family,
                source_ip=self.config.source_ip,
                timeout=self.config.timeout,
                proxy_url=self.config.proxy_url,
            )
            built = build_client_hello(
                sni=self.config.effective_sni,
                profile=self.config.profile,
            )
            self._tls = open_tls13_connection(sock, built)
            if self._tls.selected_alpn != "h2":
                raise RuntimeError(
                    f"server selected ALPN {self._tls.selected_alpn!r}, expected 'h2'"
                )

            self._sock = sock
            self._h2.initiate_connection()
            self._flush()
        except Exception:
            if sock is not None:
                sock.close()
            self._sock = None
            self._tls = None
            self._h2 = None
            raise

    def close(self) -> None:
        try:
            if self._h2 is not None and self._tls is not None:
                try:
                    self._h2.close_connection()
                    self._flush()
                except Exception:
                    pass
        finally:
            if self._sock is not None:
                try:
                    self._sock.close()
                finally:
                    self._sock = None
            self._tls = None
            self._h2 = None

    def __enter__(self) -> H2Connection:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get(self, url: str, headers: HeaderItems | None = None) -> H2Response:
        return self.request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        headers: HeaderItems | None = None,
        content: bytes | str | None = b"",
    ) -> H2Response:
        return self.request("POST", url, headers=headers, content=content)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: HeaderItems | None = None,
        content: bytes | str | None = None,
    ) -> H2Response:
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise ValueError("only GET and POST are supported")

        body = b"" if method == "GET" else _coerce_body(content)
        request_headers = build_request_headers(
            method,
            url,
            remote_host=self.config.remote_host,
            port=self.config.port,
            headers=headers,
            content_length=len(body) if method == "POST" else None,
        )
        last_exc: Exception | None = None
        for attempt in range(2):
            self._log_request(method, request_headers, body)
            try:
                response = self._request_once(request_headers, body)
                self._log_response(response)
                return response
            except Exception as exc:
                last_exc = exc
                self.close()
                if attempt == 0:
                    logger.warning(
                        "H2 request failed; reconnecting source_ip={} "
                        "method={} path={} error={}: {}",
                        self.config.source_ip or "auto",
                        method,
                        _header_value(request_headers, ":path"),
                        exc.__class__.__name__,
                        exc,
                    )
                    continue
                raise

        assert last_exc is not None
        raise last_exc

    def _request_once(
        self,
        request_headers: list[tuple[str, str]],
        body: bytes,
    ) -> H2Response:
        self.connect()
        assert self._h2 is not None
        stream_id = self._h2.get_next_available_stream_id()
        self._h2.send_headers(
            stream_id,
            request_headers,
            end_stream=(len(body) == 0),
        )
        if body:
            self._send_body(stream_id, body)
        self._flush()
        return self._read_response(stream_id)

    def _send_body(self, stream_id: int, body: bytes) -> None:
        assert self._h2 is not None
        max_frame_size = self._h2.max_outbound_frame_size
        pos = 0
        while pos < len(body):
            chunk = body[pos : pos + max_frame_size]
            pos += len(chunk)
            self._h2.send_data(
                stream_id,
                chunk,
                end_stream=(pos >= len(body)),
            )

    def _log_request(
        self,
        method: str,
        headers: list[tuple[str, str]],
        body: bytes,
    ) -> None:
        logger.debug(
            "H2 request source_ip={} method={} path={} body_len={} header={}",
            self.config.source_ip or "auto",
            method,
            _header_value(headers, ":path"),
            len(body),
            str({name: value for name, value in headers}),
        )

    def _log_response(self, response: H2Response) -> None:
        logger.debug(
            "H2 response source_ip={} stream_id={} status={} "
            "body_len={}",
            self.config.source_ip or "auto",
            response.stream_id,
            response.status,
            len(response.body),
        )

    def _flush(self) -> None:
        assert self._tls is not None
        assert self._h2 is not None
        data = self._h2.data_to_send()
        if data:
            self._tls.send_application_data(data)

    def _read_events(self):
        assert self._tls is not None
        assert self._h2 is not None
        data = self._tls.read_application_data()
        events = self._h2.receive_data(data)
        self._flush()
        return events

    def _read_response(self, stream_id: int) -> H2Response:
        assert self._h2 is not None
        response_headers: list[tuple[str, str]] = []
        response_body = bytearray()
        status: int | None = None

        while True:
            for event in self._read_events():
                if isinstance(event, ResponseReceived) and event.stream_id == stream_id:
                    response_headers.extend(event.headers)
                    for name, value in event.headers:
                        if name == ":status":
                            status = int(value)
                elif isinstance(event, TrailersReceived) and event.stream_id == stream_id:
                    response_headers.extend(event.headers)
                elif isinstance(event, DataReceived) and event.stream_id == stream_id:
                    response_body.extend(event.data)
                    self._h2.acknowledge_received_data(
                        event.flow_controlled_length,
                        event.stream_id,
                    )
                    self._flush()
                elif isinstance(event, StreamEnded) and event.stream_id == stream_id:
                    return H2Response(
                        status=status,
                        headers=response_headers,
                        body=bytes(response_body),
                        stream_id=stream_id,
                    )
                elif isinstance(event, StreamReset) and event.stream_id == stream_id:
                    raise RuntimeError(
                        f"stream reset by peer: error_code={event.error_code}"
                    )
                elif isinstance(event, ConnectionTerminated):
                    raise RuntimeError(
                        "HTTP/2 connection terminated by peer: "
                        f"error_code={event.error_code}, "
                        f"last_stream_id={event.last_stream_id}"
                    )
