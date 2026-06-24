from __future__ import annotations

import ipaddress
import json
import random
import socket
import subprocess
import threading
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

try:
    from .abstract_h2_client import AbstractH2Client
    from .constants import (
        H2CLIENT_CONNECTIONS_PER_SOURCE_IP,
        H2CLIENT_HEALTHCHECK_HOST,
        H2CLIENT_HEALTHCHECK_TIMEOUT,
        H2CLIENT_HEALTHCHECK_URL,
        H2CLIENT_SOURCE_INTERFACE_ALIASES,
    )
    from .h2connection import AddressFamily, H2Connection, H2Response
except ImportError:  # pragma: no cover - supports direct import from util/h2client.
    from abstract_h2_client import AbstractH2Client
    from constants import (
        H2CLIENT_CONNECTIONS_PER_SOURCE_IP,
        H2CLIENT_HEALTHCHECK_HOST,
        H2CLIENT_HEALTHCHECK_TIMEOUT,
        H2CLIENT_HEALTHCHECK_URL,
        H2CLIENT_SOURCE_INTERFACE_ALIASES,
    )
    from h2connection import AddressFamily, H2Connection, H2Response


HeaderItems = Mapping[str, str] | Sequence[tuple[str, str]]
SourceIPProvider = Callable[[], list["SourceAddress"]]
ConnectionFactory = Callable[..., H2Connection]
SlotChooser = Callable[[Sequence["ConnectionSlot"]], "ConnectionSlot"]
FallbackClientFactory = Callable[..., Any]


@dataclass(frozen=True)
class SourceAddress:
    ip: str
    family: AddressFamily
    interface_alias: str = ""


@dataclass
class ConnectionSlot:
    source: SourceAddress
    connection: H2Connection
    lock: threading.Lock = field(default_factory=threading.Lock)

    def close(self) -> None:
        self.connection.close()


def _is_usable_source_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return not (
        ip.is_loopback
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_link_local
    )


def _source_address(value: str, interface_alias: str = "") -> SourceAddress | None:
    if not _is_usable_source_ip(value):
        return None
    ip = ipaddress.ip_address(value.split("%", 1)[0])
    return SourceAddress(
        ip=str(ip),
        family="ipv6" if ip.version == 6 else "ipv4",
        interface_alias=interface_alias,
    )


def _dedupe_sources(sources: Sequence[SourceAddress]) -> list[SourceAddress]:
    seen: set[tuple[str, AddressFamily]] = set()
    result: list[SourceAddress] = []
    for source in sources:
        key = (source.ip, source.family)
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _discover_sources_with_powershell(
    interface_aliases: Sequence[str],
) -> list[SourceAddress] | None:
    quoted_aliases = ",".join(
        "'" + alias.replace("'", "''") + "'" for alias in interface_aliases
    )
    script = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "$OutputEncoding=[System.Text.Encoding]::UTF8; "
        f"$aliases=@({quoted_aliases}); "
        "Get-NetIPAddress -InterfaceAlias $aliases "
        "-AddressFamily IPv4,IPv6 -ErrorAction SilentlyContinue | "
        "Where-Object { $_.IPAddress } | "
        "Select-Object IPAddress,InterfaceAlias | "
        "ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    if not completed.stdout.strip():
        return []

    payload = json.loads(completed.stdout)
    rows = payload if isinstance(payload, list) else [payload]
    sources: list[SourceAddress] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ip = str(row.get("IPAddress") or "")
        alias = str(row.get("InterfaceAlias") or "")
        source = _source_address(ip, alias)
        if source is not None:
            sources.append(source)
    return _dedupe_sources(sources)


def _discover_sources_with_socket() -> list[SourceAddress]:
    sources: list[SourceAddress] = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_UNSPEC)
    except OSError:
        return []

    for family, _, _, _, sockaddr in infos:
        if family == socket.AF_INET:
            ip = sockaddr[0]
        elif family == socket.AF_INET6:
            ip = sockaddr[0]
        else:
            continue
        source = _source_address(ip)
        if source is not None:
            sources.append(source)
    return _dedupe_sources(sources)


def discover_interface_source_ips(
    interface_aliases: Sequence[str] = H2CLIENT_SOURCE_INTERFACE_ALIASES,
) -> list[SourceAddress]:
    try:
        sources = _discover_sources_with_powershell(interface_aliases)
    except Exception:
        sources = None
    if sources is not None:
        return sources
    return _discover_sources_with_socket()


def _append_params(url: str, params: Any) -> str:
    if not params:
        return url
    parsed = urllib.parse.urlsplit(url)
    query = parsed.query
    if isinstance(params, str):
        new_query = params
    else:
        new_query = urllib.parse.urlencode(params, doseq=True)
    query = f"{query}&{new_query}" if query and new_query else query or new_query
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
    )


def _json_body(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _form_body(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return urllib.parse.urlencode(value, doseq=True).encode("utf-8")


def _header_mapping(headers: HeaderItems | None) -> httpx.Headers:
    return httpx.Headers(headers or {})


def _set_default_header(headers: httpx.Headers, name: str, value: str) -> None:
    if name not in headers:
        headers[name] = value


def _timeout_seconds(timeout: Any, default: float) -> float:
    if timeout is None:
        return default
    if isinstance(timeout, (int, float)):
        return float(timeout)
    values = [
        value
        for value in (
            getattr(timeout, "connect", None),
            getattr(timeout, "read", None),
            getattr(timeout, "write", None),
        )
        if isinstance(value, (int, float))
    ]
    return float(max(values)) if values else default


def _content_length(content: bytes | str | None) -> int:
    if content is None:
        return 0
    if isinstance(content, bytes):
        return len(content)
    return len(content.encode("utf-8"))


class RotatingIPJA3H2Client(AbstractH2Client):
    def __init__(
        self,
        *,
        http2: bool = True,
        verify: bool | str = True,
        proxy: str | None = None,
        timeout: Any = None,
        limits: Any = None,
        headers: HeaderItems | None = None,
        cookies: Any = None,
        interface_aliases: Sequence[str] = H2CLIENT_SOURCE_INTERFACE_ALIASES,
        connections_per_source_ip: int = H2CLIENT_CONNECTIONS_PER_SOURCE_IP,
        healthcheck_url: str = H2CLIENT_HEALTHCHECK_URL,
        healthcheck_host: str = H2CLIENT_HEALTHCHECK_HOST,
        source_ip_provider: SourceIPProvider | None = None,
        connection_factory: ConnectionFactory = H2Connection,
        slot_chooser: SlotChooser | None = None,
        fallback_client_factory: FallbackClientFactory = httpx.Client,
        **_: Any,
    ) -> None:
        if not http2:
            raise ValueError("RotatingIPJA3H2Client only supports HTTP/2")

        self.http2 = http2
        self.verify = verify
        self.proxy = proxy
        self.limits = limits
        fallback_kwargs: dict[str, Any] = {
            "http2": http2,
            "verify": verify,
            "headers": headers,
            "cookies": cookies,
        }
        if proxy is not None:
            fallback_kwargs["proxy"] = proxy
        if timeout is not None:
            fallback_kwargs["timeout"] = timeout
        if limits is not None:
            fallback_kwargs["limits"] = limits
        self._fallback_client = fallback_client_factory(**fallback_kwargs)
        self._headers = self._fallback_client.headers
        self._cookies = self._fallback_client.cookies
        self._interface_aliases = tuple(interface_aliases)
        self._connections_per_source_ip = max(1, int(connections_per_source_ip))
        self._healthcheck_url = healthcheck_url
        self._healthcheck_host = healthcheck_host
        self._timeout = _timeout_seconds(timeout, H2CLIENT_HEALTHCHECK_TIMEOUT)
        self._source_ip_provider = source_ip_provider or (
            lambda: discover_interface_source_ips(self._interface_aliases)
        )
        self._connection_factory = connection_factory
        self._slot_chooser = slot_chooser or random.choice
        self._lock = threading.RLock()
        self._available_sources: list[SourceAddress] = []
        self._pools: dict[tuple[str, int], list[ConnectionSlot]] = {}

        try:
            self._init_healthchecked_pool()
        except Exception:
            self._fallback_client.close()
            raise

    @property
    def headers(self) -> httpx.Headers:
        return self._headers

    @property
    def cookies(self) -> httpx.Cookies:
        return self._cookies

    @property
    def available_source_ips(self) -> list[str]:
        return [source.ip for source in self._available_sources]

    def close(self) -> None:
        with self._lock:
            slots = [
                slot
                for pool in self._pools.values()
                for slot in pool
            ]
            self._pools.clear()
            self._available_sources.clear()
        for slot in slots:
            slot.close()
        self._fallback_client.close()

    def head(self, url: str) -> httpx.Response:
        if self._should_use_fallback(url):
            return self._fallback_client.head(url)
        response = self.get(url)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=b"",
            request=response.request,
        )

    def get(
        self,
        url: str,
        *,
        params: Any = None,
        headers: HeaderItems | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        if self._should_use_fallback(url):
            return self._fallback_client.get(
                url,
                params=params,
                headers=headers,
                **kwargs,
            )
        return self._request("GET", _append_params(url, params), headers=headers)

    def post(
        self,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        content: bytes | str | None = None,
        headers: HeaderItems | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        if self._should_use_fallback(url):
            return self._fallback_client.post(
                url,
                data=data,
                json=json,
                content=content,
                headers=headers,
                **kwargs,
            )
        request_headers = _header_mapping(headers)
        if json is not None:
            body = _json_body(json)
            _set_default_header(request_headers, "content-type", "application/json")
        elif content is not None:
            body = content if isinstance(content, bytes) else content.encode("utf-8")
        else:
            body = _form_body(data)
            if data is not None and not isinstance(data, (bytes, str)):
                _set_default_header(
                    request_headers,
                    "content-type",
                    "application/x-www-form-urlencoded",
                )
        return self._request("POST", url, headers=request_headers, content=body)

    def _should_use_fallback(self, url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.hostname or "").lower() != self._healthcheck_host.lower()

    def _init_healthchecked_pool(self) -> None:
        sources = _dedupe_sources(self._source_ip_provider())
        if not sources:
            raise httpx.ConnectError("no usable local source IPs were discovered")

        key = (self._healthcheck_host, 443)
        healthchecked_slots: list[ConnectionSlot] = []
        available_sources: list[SourceAddress] = []

        for source in sources:
            source_ok = False
            for _ in range(self._connections_per_source_ip):
                connection = self._build_connection(self._healthcheck_host, 443, source)
                slot = ConnectionSlot(source=source, connection=connection)
                try:
                    response = connection.get(
                        self._healthcheck_url,
                        headers=self._request_headers("GET", self._healthcheck_url),
                    )
                    if response.status is not None and response.status < 500:
                        healthchecked_slots.append(slot)
                        source_ok = True
                    else:
                        slot.close()
                except Exception:
                    slot.close()
            if source_ok:
                available_sources.append(source)

        if not healthchecked_slots:
            raise httpx.ConnectError("no local source IP passed H2 healthcheck")

        self._available_sources = available_sources
        self._pools[key] = healthchecked_slots

    def _build_connection(
        self,
        host: str,
        port: int,
        source: SourceAddress,
    ) -> H2Connection:
        return self._connection_factory(
            host,
            source.ip,
            port=port,
            sni=host,
            family=source.family,
            timeout=self._timeout,
            assert_ja=True,
        )

    def _ensure_pool(self, host: str, port: int) -> list[ConnectionSlot]:
        key = (host, port)
        with self._lock:
            pool = self._pools.get(key)
            if pool:
                return pool

            pool = []
            for source in self._available_sources:
                for _ in range(self._connections_per_source_ip):
                    pool.append(
                        ConnectionSlot(
                            source=source,
                            connection=self._build_connection(host, port, source),
                        )
                    )
            if not pool:
                raise httpx.ConnectError(f"no available H2 connections for {host}")
            self._pools[key] = pool
            return pool

    def _discard_slot(
        self,
        host: str,
        port: int,
        slot: ConnectionSlot,
    ) -> None:
        with self._lock:
            pool = self._pools.get((host, port), [])
            if slot in pool:
                pool.remove(slot)
        slot.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: HeaderItems | None = None,
        content: bytes | str | None = None,
    ) -> httpx.Response:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("only absolute https:// URLs are supported")
        host = parsed.hostname
        port = parsed.port or 443
        request = httpx.Request(method, url)
        request_headers = self._request_headers(
            method,
            url,
            headers=headers,
            content=content,
        )

        last_exc: Exception | None = None
        failed_sources: set[str] = set()
        while True:
            pool = [
                slot
                for slot in self._ensure_pool(host, port)
                if slot.source.ip not in failed_sources
            ]
            if not pool:
                break

            slot = self._slot_chooser(pool)
            try:
                with slot.lock:
                    if method == "GET":
                        h2_response = slot.connection.get(url, headers=request_headers)
                    else:
                        h2_response = slot.connection.post(
                            url,
                            headers=request_headers,
                            content=content,
                        )
                return self._to_httpx_response(request, h2_response)
            except Exception as exc:
                last_exc = exc
                failed_sources.add(slot.source.ip)
                self._discard_slot(host, port, slot)

        raise self._to_httpx_error(method, url, last_exc)

    def _request_headers(
        self,
        method: str,
        url: str,
        headers: HeaderItems | None = None,
        content: bytes | str | None = None,
    ) -> httpx.Headers:
        request_headers = httpx.Headers(self._headers)
        request_headers.update(headers or {})
        request = httpx.Request(method, url, headers=request_headers)
        self._cookies.set_cookie_header(request)
        if method.upper() == "POST":
            request.headers["content-length"] = str(_content_length(content))
        return request.headers

    def _to_httpx_response(
        self,
        request: httpx.Request,
        response: H2Response,
    ) -> httpx.Response:
        headers = [
            (name, value)
            for name, value in response.headers
            if not name.startswith(":")
        ]
        return httpx.Response(
            response.status or 0,
            headers=headers,
            content=response.body,
            request=request,
        )

    def _to_httpx_error(
        self,
        method: str,
        url: str,
        exc: Exception | None,
    ) -> httpx.HTTPError:
        request = httpx.Request(method, url)
        if exc is None:
            return httpx.ConnectError("no available H2 connections", request=request)
        message = str(exc) or exc.__class__.__name__
        if isinstance(exc, (socket.timeout, TimeoutError)):
            return httpx.TimeoutException(message, request=request)
        if isinstance(exc, OSError):
            return httpx.ConnectError(message, request=request)
        return httpx.LocalProtocolError(message, request=request)
