from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import requests


class ProxyApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxyApiResult:
    proxies: list[str]
    response: dict[str, Any]


def normalize_proxy_api_protocol(protocol: str | None) -> str:
    text = str(protocol or "http").strip().lower()
    if text in {"socks", "socks5"}:
        return "socks5"
    return "http"


def build_proxy_api_url(api_url: str, *, count: int, protocol: str) -> str:
    target = str(api_url or "").strip()
    if not target:
        raise ProxyApiError("请先填写代理 API 地址")

    parts = urlsplit(target)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["count"] = str(max(1, int(count)))
    query["format"] = "json"
    query["protocol"] = normalize_proxy_api_protocol(protocol)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, doseq=True),
            parts.fragment,
        )
    )


def _iter_proxy_items(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("proxy_list", "list", "proxies", "items"):
                value = data.get(key)
                if isinstance(value, list):
                    return value
            if any(key in data for key in ("ip", "host", "port", "proxy")):
                return [data]
        elif isinstance(data, list):
            return data

        for key in ("proxy_list", "list", "proxies", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    if isinstance(payload, list):
        return payload
    return []


def _normalize_proxy_scheme(scheme: str | None, fallback_protocol: str) -> str:
    text = str(scheme or "").strip().lower()
    if text in {"socks", "socks5"}:
        return "socks5"
    if text == "socks4":
        return "socks4"
    if text in {"http", "https"}:
        return text
    return normalize_proxy_api_protocol(fallback_protocol)


def _format_proxy_url(
    *,
    scheme: str,
    host: str,
    port: str,
    username: str = "",
    password: str = "",
) -> str:
    host = str(host or "").strip()
    port = str(port or "").strip()
    username = str(username or "").strip()
    password = str(password or "")
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        host = f"[{host}]"
    if username:
        auth = quote(username, safe="")
        if password:
            auth = f"{auth}:{quote(password, safe='')}"
        return f"{scheme}://{auth}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


def _get_any_key(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    lower_item = {str(key).lower(): value for key, value in item.items()}
    for key in keys:
        value = lower_item.get(key.lower())
        if value is not None:
            return value
    return None


def _extract_proxy_parts(
    item: Any,
    *,
    protocol: str,
) -> tuple[str, str, str, str, str] | None:
    if isinstance(item, dict):
        proxy_value = _get_any_key(item, "proxy", "addr", "address")
        if proxy_value:
            proxy_parts = _extract_proxy_parts(str(proxy_value), protocol=protocol)
            if proxy_parts is None:
                return None
            scheme, host, port, username, password = proxy_parts
            if username:
                return proxy_parts
            username = (
                _get_any_key(item, "username", "user", "account", "authkey")
                or ""
            )
            password = (
                _get_any_key(item, "password", "pass", "pwd", "authpwd")
                or ""
            )
            scheme = _normalize_proxy_scheme(
                _get_any_key(item, "protocol", "scheme", "type") or scheme,
                protocol,
            )
            return (
                scheme,
                host,
                port,
                str(username).strip(),
                str(password),
            )

        host = _get_any_key(item, "ip", "host")
        port = _get_any_key(item, "port")
        if host and port:
            username = (
                _get_any_key(item, "username", "user", "account", "authkey")
                or ""
            )
            password = (
                _get_any_key(item, "password", "pass", "pwd", "authpwd")
                or ""
            )
            scheme = _normalize_proxy_scheme(
                _get_any_key(item, "protocol", "scheme", "type"),
                protocol,
            )
            return (
                scheme,
                str(host).strip(),
                str(port).strip(),
                str(username).strip(),
                str(password),
            )
        return None

    text = str(item or "").strip()
    if not text:
        return None

    parsed = urlsplit(text)
    if parsed.scheme and parsed.netloc:
        try:
            port = parsed.port
        except ValueError:
            port = None
        if parsed.hostname and port:
            return (
                _normalize_proxy_scheme(parsed.scheme, protocol),
                parsed.hostname.strip(),
                str(port),
                unquote(parsed.username or "").strip(),
                unquote(parsed.password or ""),
            )

    scheme = normalize_proxy_api_protocol(protocol)
    schema_match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://(.+)$", text)
    if schema_match:
        scheme = _normalize_proxy_scheme(schema_match.group(1), protocol)
        text = schema_match.group(2)

    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    username = ""
    password = ""
    if "@" in text:
        auth, text = text.rsplit("@", 1)
        username, _, password = auth.partition(":")

    parts = text.split(":")
    if len(parts) >= 4:
        return (
            scheme,
            parts[0].strip(),
            parts[1].strip(),
            username or parts[2].strip(),
            password or ":".join(parts[3:]),
        )

    if ":" not in text:
        return None
    host, port = text.rsplit(":", 1)
    return scheme, host.strip(), port.strip(), username.strip(), password


def parse_proxy_api_response(payload: dict[str, Any], *, protocol: str) -> list[str]:
    code = payload.get("code", payload.get("errno", 0))
    success = payload.get("success")
    if success is False or str(code) not in {"0", "200", "None"}:
        message = payload.get("msg") or payload.get("message") or payload
        raise ProxyApiError(f"代理 API 返回失败: {message}")

    proxies: list[str] = []
    seen: set[str] = set()
    for item in _iter_proxy_items(payload):
        proxy_parts = _extract_proxy_parts(item, protocol=protocol)
        if not proxy_parts:
            continue
        scheme, host, port, username, password = proxy_parts
        if not host or not port.isdigit():
            continue
        proxy = _format_proxy_url(
            scheme=scheme,
            host=host,
            port=port,
            username=username,
            password=password,
        )
        key = proxy.lower()
        if key in seen:
            continue
        seen.add(key)
        proxies.append(proxy)

    if not proxies:
        raise ProxyApiError("代理 API 返回成功，但没有解析到代理 IP 和端口")
    return proxies


def fetch_proxy_api(
    api_url: str,
    *,
    count: int,
    protocol: str,
    timeout: int = 15,
) -> ProxyApiResult:
    request_url = build_proxy_api_url(api_url, count=count, protocol=protocol)
    response = requests.request(
        "GET", request_url, headers={}, data={}, timeout=timeout
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ProxyApiError("代理 API 未返回 JSON 对象")
    return ProxyApiResult(
        proxies=parse_proxy_api_response(payload, protocol=protocol),
        response=payload,
    )
