from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def _extract_host_port(item: Any) -> tuple[str, str] | None:
    if isinstance(item, dict):
        proxy_value = item.get("proxy") or item.get("addr") or item.get("address")
        if proxy_value:
            return _extract_host_port(str(proxy_value))

        host = item.get("ip") or item.get("host")
        port = item.get("port")
        if host and port:
            return str(host).strip(), str(port).strip()
        return None

    text = str(item or "").strip()
    if not text:
        return None
    text = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", text)
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if ":" not in text:
        return None
    host, port = text.rsplit(":", 1)
    return host.strip(), port.strip()


def parse_proxy_api_response(payload: dict[str, Any], *, protocol: str) -> list[str]:
    code = payload.get("code", payload.get("errno", 0))
    success = payload.get("success")
    if success is False or str(code) not in {"0", "200", "None"}:
        message = payload.get("msg") or payload.get("message") or payload
        raise ProxyApiError(f"代理 API 返回失败: {message}")

    scheme = "socks" if normalize_proxy_api_protocol(protocol) == "socks5" else "http"
    proxies: list[str] = []
    seen: set[str] = set()
    for item in _iter_proxy_items(payload):
        host_port = _extract_host_port(item)
        if not host_port:
            continue
        host, port = host_port
        if not host or not port.isdigit():
            continue
        proxy = f"{scheme}://{host}:{port}"
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
    response = requests.request("GET", request_url, headers={}, data={}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ProxyApiError("代理 API 未返回 JSON 对象")
    return ProxyApiResult(
        proxies=parse_proxy_api_response(payload, protocol=protocol),
        response=payload,
    )
