from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import requests


class ProxyApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxyApiProfile:
    name: str
    host_keywords: tuple[str, ...] = ()
    count_keys: tuple[str, ...] = ()
    format_defaults: tuple[tuple[str, str], ...] = ()
    protocol_defaults: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()
    success_codes: tuple[str, ...] = ("0", "1", "200", "10000", "success", "ok")
    fill_missing_params: bool = True


@dataclass(frozen=True)
class ProxyApiRequest:
    url: str
    profile: ProxyApiProfile


@dataclass(frozen=True)
class ProxyApiResult:
    proxies: list[str]
    response: dict[str, Any]
    proxy_records: list[dict[str, Any]] | None = None


_COMMON_COUNT_KEYS = ("count", "num", "cnt", "getnum")
_COMMON_FORMAT_DEFAULTS = (
    ("format", "json"),
    ("type", "2"),
    ("wt", "json"),
    ("result_type", "json"),
    ("datatype", "json"),
)
_COMMON_PROTOCOL_DEFAULTS = (
    ("protocol", (("http", "http"), ("socks5", "socks5"))),
)

_PROFILES: tuple[ProxyApiProfile, ...] = (
    ProxyApiProfile(
        name="youdaili",
        host_keywords=("youdaili.com",),
        count_keys=("count",),
        format_defaults=(("format", "json"),),
        protocol_defaults=_COMMON_PROTOCOL_DEFAULTS,
    ),
    ProxyApiProfile(
        name="kuaidaili",
        host_keywords=("kdlapi.com", "kuaidaili.com"),
        count_keys=("num",),
        format_defaults=(("format", "json"),),
    ),
    ProxyApiProfile(
        name="zhima",
        host_keywords=("zhimacangku.com", "zhimahttp.com", "zmhttp.com"),
        count_keys=("num",),
        format_defaults=(("type", "2"),),
    ),
    ProxyApiProfile(
        name="xiaoxiang",
        host_keywords=("xiaoxiangdaili.com",),
        count_keys=("cnt",),
        format_defaults=(("wt", "json"),),
    ),
    ProxyApiProfile(
        name="xiequ",
        host_keywords=("xiequ.cn",),
        count_keys=("num",),
        format_defaults=(("type", "2"),),
    ),
    ProxyApiProfile(
        name="juliang",
        host_keywords=("juliangip.com",),
        count_keys=("num",),
        format_defaults=(("result_type", "json"),),
    ),
    ProxyApiProfile(
        name="qingguo",
        host_keywords=("qg.net", "qingguo", "qingguodaili"),
        count_keys=("num", "count"),
    ),
    ProxyApiProfile(
        name="yiniuyun",
        host_keywords=("16yun.cn", "yiniuyun"),
        count_keys=("num", "count"),
    ),
    ProxyApiProfile(
        name="pinyi",
        host_keywords=("pyhttp", "pinyi", "taolop.com"),
        count_keys=("count", "num"),
    ),
    ProxyApiProfile(
        name="taiyang",
        host_keywords=("taiyang", "taiyangdaili"),
        count_keys=("num", "count"),
    ),
    ProxyApiProfile(
        name="mogu",
        host_keywords=("mogu", "mogumiao"),
        count_keys=("num", "count"),
    ),
    ProxyApiProfile(
        name="xundaili",
        host_keywords=("xundaili",),
        count_keys=("num", "count"),
    ),
    ProxyApiProfile(
        name="zdaye",
        host_keywords=("zdaye.com",),
        count_keys=("count", "num"),
        format_defaults=(("returnType", "2"),),
        success_codes=("10001",),
    ),
    ProxyApiProfile(
        name="duomi",
        host_keywords=("duomi", "duoip"),
        count_keys=("getnum", "num", "count"),
    ),
)

_GENERIC_PROFILE = ProxyApiProfile(
    name="generic",
    host_keywords=(),
    count_keys=_COMMON_COUNT_KEYS,
    format_defaults=_COMMON_FORMAT_DEFAULTS,
    protocol_defaults=_COMMON_PROTOCOL_DEFAULTS,
    fill_missing_params=False,
)

_SUCCESS_CODES = {"0", "1", "200", "10000", "success", "ok", "true", "none", ""}
_CODE_KEYS = (
    "code",
    "errno",
    "errorcode",
    "error_code",
    "status",
    "status_code",
    "ret",
)
_SUCCESS_KEYS = ("success", "ok")
_MESSAGE_KEYS = (
    "msg",
    "message",
    "errmsg",
    "errormsg",
    "error_msg",
    "error",
    "reason",
    "desc",
)
_PROXY_VALUE_KEYS = (
    "proxy",
    "addr",
    "address",
    "ipport",
    "ip_port",
    "server",
    "proxyip",
    "proxy_ip",
    "ip_port_str",
)
_HOST_KEYS = ("ip", "host", "hostname", "proxy_ip", "proxyip")
_PORT_KEYS = ("port", "proxy_port", "proxyport")
_USERNAME_KEYS = (
    "username",
    "user",
    "account",
    "authkey",
    "auth_key",
    "userid",
    "user_name",
)
_PASSWORD_KEYS = (
    "password",
    "pass",
    "pwd",
    "authpwd",
    "auth_pwd",
    "passwd",
)
_SCHEME_KEYS = ("protocol", "scheme", "proxy_type", "proxytype", "httptype")
_TTL_KEYS = (
    "ttl",
    "life",
    "lifetime",
    "survival",
    "expire",
    "expires",
    "expired",
    "expire_time",
    "expiretime",
    "deadline",
    "valid_time",
    "validtime",
)
_SENSITIVE_QUERY_KEYS = {
    "appkey",
    "app_key",
    "appsecret",
    "app_secret",
    "auth",
    "authkey",
    "authpwd",
    "key",
    "pack",
    "password",
    "passwd",
    "pwd",
    "secret",
    "secret_id",
    "sign",
    "signature",
    "token",
    "trade_no",
    "uid",
    "user",
    "username",
    "vkey",
}
_HOST_PATTERN = r"(?:\d{1,3}(?:\.\d{1,3}){3}|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+|\[[0-9A-Fa-f:.]+\])"
_URL_CANDIDATE_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s,;|]+")
_PROXY_CANDIDATE_RE = re.compile(
    rf"(?:[^\s:@,;|]+(?::[^\s@,;|]*)?@)?{_HOST_PATTERN}:\d{{2,5}}"
    rf"(?::[^\s,;|]+(?::[^\s,;|]+)?)?"
)


def normalize_proxy_api_protocol(protocol: str | None) -> str:
    text = str(protocol or "http").strip().lower()
    if text == "auto":
        return "auto"
    if text in {"socks", "socks5"}:
        return "socks5"
    return "http"


def mask_proxy_api_url(api_url: str) -> str:
    target = str(api_url or "").strip()
    if not target:
        return ""
    parts = urlsplit(target)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        query.append((key, "***" if key.lower() in _SENSITIVE_QUERY_KEYS else value))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, doseq=True, safe="*"),
            parts.fragment,
        )
    )


def _normalize_count(count: int) -> int:
    try:
        return max(1, int(count))
    except (TypeError, ValueError):
        return 1


def detect_proxy_api_profile(api_url: str) -> ProxyApiProfile:
    target = str(api_url or "").strip().lower()
    parts = urlsplit(target)
    haystack = f"{parts.netloc}{parts.path}"
    for profile in _PROFILES:
        if any(keyword in haystack for keyword in profile.host_keywords):
            return profile
    return _GENERIC_PROFILE


def _query_has_key(query: list[tuple[str, str]], keys: tuple[str, ...]) -> bool:
    lower_keys = {key.lower() for key in keys}
    return any(key.lower() in lower_keys for key, _value in query)


def _fill_query_keys(
    query: list[tuple[str, str]],
    keys: tuple[str, ...],
    value: str,
    *,
    allow_missing: bool,
) -> bool:
    lower_keys = {key.lower() for key in keys}
    found = False
    for index, (key, current_value) in enumerate(query):
        if key.lower() not in lower_keys:
            continue
        found = True
        if str(current_value).strip() == "":
            query[index] = (key, value)
            return True
        break
    if allow_missing and not found and keys:
        query.append((keys[0], value))
        return True
    return False


def _fill_query_defaults(
    query: list[tuple[str, str]],
    defaults: tuple[tuple[str, str], ...],
    *,
    allow_missing: bool,
) -> bool:
    if not defaults:
        return False
    matched_existing_key = False
    for default_key, default_value in defaults:
        for index, (key, current_value) in enumerate(query):
            if key.lower() != default_key.lower():
                continue
            matched_existing_key = True
            if str(current_value).strip() == "":
                query[index] = (key, default_value)
                return True
            break
    if allow_missing and not matched_existing_key:
        query.append(defaults[0])
        return True
    return False


def _fill_protocol_defaults(
    query: list[tuple[str, str]],
    defaults: tuple[tuple[str, tuple[tuple[str, str], ...]], ...],
    *,
    protocol: str,
    allow_missing: bool,
) -> bool:
    if not defaults:
        return False
    normalized_protocol = normalize_proxy_api_protocol(protocol)
    matched_existing_key = False
    for key, mapping_items in defaults:
        mapping = dict(mapping_items)
        value = mapping.get(normalized_protocol)
        if value is None:
            continue
        for index, (current_key, current_value) in enumerate(query):
            if current_key.lower() != key.lower():
                continue
            matched_existing_key = True
            if str(current_value).strip() == "":
                query[index] = (current_key, value)
                return True
            break
    if allow_missing and not matched_existing_key:
        key, mapping_items = defaults[0]
        value = dict(mapping_items).get(normalized_protocol)
        if value is not None:
            query.append((key, value))
            return True
    return False


def build_proxy_api_request(
    api_url: str,
    *,
    count: int,
    protocol: str,
) -> ProxyApiRequest:
    target = str(api_url or "").strip()
    if not target:
        raise ProxyApiError("请先填写代理 API 地址")

    profile = detect_proxy_api_profile(target)
    parts = urlsplit(target)
    query = parse_qsl(parts.query, keep_blank_values=True)
    allow_missing = profile.fill_missing_params
    count_value = str(_normalize_count(count))

    changed = _fill_query_keys(
        query,
        profile.count_keys,
        count_value,
        allow_missing=allow_missing,
    )
    changed = (
        _fill_query_defaults(
            query,
            profile.format_defaults,
            allow_missing=allow_missing,
        )
        or changed
    )
    changed = (
        _fill_protocol_defaults(
            query,
            profile.protocol_defaults,
            protocol=protocol,
            allow_missing=allow_missing,
        )
        or changed
    )

    if not changed:
        return ProxyApiRequest(url=target, profile=profile)

    request_url = urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query, doseq=True),
            parts.fragment,
        )
    )
    return ProxyApiRequest(url=request_url, profile=profile)


def build_proxy_api_url(api_url: str, *, count: int, protocol: str) -> str:
    return build_proxy_api_request(api_url, count=count, protocol=protocol).url


def _normalize_proxy_scheme(scheme: str | None, fallback_protocol: str) -> str:
    text = str(scheme or "").strip().lower()
    if text in {"socks", "socks5", "socks5h"}:
        return "socks5"
    if text == "socks4":
        return "socks4"
    if text in {"http", "https"}:
        return text
    normalized_fallback = normalize_proxy_api_protocol(fallback_protocol)
    if normalized_fallback == "auto":
        return "http"
    return normalized_fallback


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


def _is_valid_port(port: str) -> bool:
    if not str(port or "").isdigit():
        return False
    value = int(port)
    return 1 <= value <= 65535


def _parse_host_port_auth_text(
    text: str,
    *,
    protocol: str,
) -> tuple[str, str, str, str, str] | None:
    value = text.strip().strip("\"'<>")
    if not value:
        return None

    scheme = _normalize_proxy_scheme(None, protocol)
    scheme_match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://(.+)$", value)
    if scheme_match:
        scheme = _normalize_proxy_scheme(scheme_match.group(1), protocol)
        value = scheme_match.group(2)

    value = value.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    username = ""
    password = ""
    if "@" in value:
        auth, value = value.rsplit("@", 1)
        username, _, password = auth.partition(":")
        username = unquote(username).strip()
        password = unquote(password)

    bracketed_ipv6 = re.match(r"^\[([0-9A-Fa-f:.]+)]:(\d{1,5})(?::(.*))?$", value)
    if bracketed_ipv6:
        extra_username = ""
        extra_password = ""
        if bracketed_ipv6.group(3):
            extra_username, _, extra_password = bracketed_ipv6.group(3).partition(":")
        return (
            scheme,
            bracketed_ipv6.group(1),
            bracketed_ipv6.group(2),
            username or extra_username.strip(),
            password or extra_password,
        )

    parts = value.split(":")
    if len(parts) >= 4 and parts[1].isdigit():
        return (
            scheme,
            parts[0].strip(),
            parts[1].strip(),
            username or parts[2].strip(),
            password or ":".join(parts[3:]),
        )

    if ":" not in value:
        return None
    host, port = value.rsplit(":", 1)
    if ":" in host and "::" in host:
        return scheme, host.strip(), port.strip(), username, password
    return scheme, host.strip(), port.strip(), username, password


def _extract_proxy_parts(
    item: Any,
    *,
    protocol: str,
) -> tuple[str, str, str, str, str] | None:
    if isinstance(item, dict):
        proxy_value = _get_any_key(item, *_PROXY_VALUE_KEYS)
        if proxy_value:
            proxy_parts = _extract_proxy_parts(str(proxy_value), protocol=protocol)
            if proxy_parts is None:
                return None
            scheme, host, port, username, password = proxy_parts
            if username:
                return proxy_parts
            username = _get_any_key(item, *_USERNAME_KEYS) or ""
            password = _get_any_key(item, *_PASSWORD_KEYS) or ""
            scheme = _normalize_proxy_scheme(
                _get_any_key(item, *_SCHEME_KEYS) or scheme,
                protocol,
            )
            return (
                scheme,
                host,
                port,
                str(username).strip(),
                str(password),
            )

        host = _get_any_key(item, *_HOST_KEYS)
        port = _get_any_key(item, *_PORT_KEYS)
        if host is not None and port is not None:
            username = _get_any_key(item, *_USERNAME_KEYS) or ""
            password = _get_any_key(item, *_PASSWORD_KEYS) or ""
            scheme = _normalize_proxy_scheme(_get_any_key(item, *_SCHEME_KEYS), protocol)
            return (
                scheme,
                str(host).strip().strip("[]"),
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

    return _parse_host_port_auth_text(text, protocol=protocol)


def _extract_ttl_metadata(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    metadata = {}
    for key in _TTL_KEYS:
        value = _get_any_key(item, key)
        if value not in (None, ""):
            metadata[key] = value
    return metadata


def _coerce_profile(profile: ProxyApiProfile | str | None) -> ProxyApiProfile:
    if isinstance(profile, ProxyApiProfile):
        return profile
    if isinstance(profile, str):
        for candidate in _PROFILES:
            if candidate.name == profile:
                return candidate
    return _GENERIC_PROFILE


def _message_from_payload(payload: dict[str, Any]) -> str:
    message = _get_any_key(payload, *_MESSAGE_KEYS)
    if message not in (None, ""):
        return str(message)
    return str(payload)


def _raise_if_provider_failure(payload: Any, profile: ProxyApiProfile) -> None:
    if not isinstance(payload, dict):
        return

    success_value = _get_any_key(payload, *_SUCCESS_KEYS)
    if success_value is False or str(success_value).strip().lower() == "false":
        raise ProxyApiError(f"代理 API 返回失败: {_message_from_payload(payload)}")

    code_found = False
    code_value: Any = None
    for key in _CODE_KEYS:
        value = _get_any_key(payload, key)
        if value is not None:
            code_found = True
            code_value = value
            break

    if not code_found:
        return

    success_codes = _SUCCESS_CODES | {str(code).strip().lower() for code in profile.success_codes}
    code_text = str(code_value).strip().lower()
    if code_text not in success_codes:
        raise ProxyApiError(f"代理 API 返回失败: {_message_from_payload(payload)}")


def _add_proxy(
    proxies: list[str],
    seen: set[str],
    proxy_parts: tuple[str, str, str, str, str] | None,
    records: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not proxy_parts:
        return
    scheme, host, port, username, password = proxy_parts
    if not host or not _is_valid_port(port):
        return
    proxy = _format_proxy_url(
        scheme=scheme,
        host=host,
        port=port,
        username=username,
        password=password,
    )
    key = proxy.lower()
    if key in seen:
        return
    seen.add(key)
    proxies.append(proxy)
    if records is not None:
        record: dict[str, Any] = {
            "proxy": proxy,
            "host": host,
            "port": port,
            "scheme": scheme,
        }
        if username:
            record["username"] = username
        if metadata:
            record.update(metadata)
        records.append(record)


def _csv_row_to_item(header: list[str], row: list[str]) -> dict[str, str] | None:
    if not header or len(row) < 2:
        return None
    lower_header = [column.strip().lower() for column in header]
    if not any(column in {"ip", "host", "hostname"} for column in lower_header):
        return None
    if "port" not in lower_header and "proxy_port" not in lower_header:
        return None
    return {
        header[index].strip(): row[index].strip()
        for index in range(min(len(header), len(row)))
        if header[index].strip()
    }


def _split_csv_line(line: str) -> list[str]:
    return [part.strip() for part in line.split(",")]


def _collect_from_text(
    text: str,
    *,
    protocol: str,
    proxies: list[str],
    seen: set[str],
    records: list[dict[str, Any]] | None = None,
) -> None:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    csv_header: list[str] | None = None
    for line in lines:
        if "," in line:
            columns = _split_csv_line(line)
            if csv_header is not None:
                _add_proxy(
                    proxies,
                    seen,
                    _extract_proxy_parts(
                        _csv_row_to_item(csv_header, columns) or "",
                        protocol=protocol,
                    ),
                    records,
                )
                continue
            lower_columns = [column.lower() for column in columns]
            if any(column in {"ip", "host", "hostname"} for column in lower_columns):
                csv_header = columns
                continue
            if len(columns) >= 4 and _is_valid_port(columns[1]):
                _add_proxy(
                    proxies,
                    seen,
                    _extract_proxy_parts(
                        {
                            "ip": columns[0],
                            "port": columns[1],
                            "username": columns[2],
                            "password": columns[3],
                        },
                        protocol=protocol,
                    ),
                    records,
                )

        url_matches = list(_URL_CANDIDATE_RE.finditer(line))
        url_spans = [match.span() for match in url_matches]
        candidates = [match.group(0) for match in url_matches]
        for match in _PROXY_CANDIDATE_RE.finditer(line):
            start, end = match.span()
            if any(span_start <= start and end <= span_end for span_start, span_end in url_spans):
                continue
            candidates.append(match.group(0))
        if not candidates:
            candidates.append(line)
        for candidate in candidates:
            _add_proxy(
                proxies,
                seen,
                _extract_proxy_parts(candidate, protocol=protocol),
                records,
            )


def _collect_from_payload(
    payload: Any,
    *,
    protocol: str,
    proxies: list[str],
    seen: set[str],
    records: list[dict[str, Any]] | None = None,
    depth: int = 0,
) -> None:
    if depth > 8:
        return
    if isinstance(payload, dict):
        proxy_parts = _extract_proxy_parts(payload, protocol=protocol)
        _add_proxy(
            proxies,
            seen,
            proxy_parts,
            records,
            _extract_ttl_metadata(payload),
        )
        for value in payload.values():
            if proxy_parts is not None and not isinstance(value, (dict, list)):
                continue
            _collect_from_payload(
                value,
                protocol=protocol,
                proxies=proxies,
                seen=seen,
                records=records,
                depth=depth + 1,
            )
        return
    if isinstance(payload, list):
        for item in payload:
            _collect_from_payload(
                item,
                protocol=protocol,
                proxies=proxies,
                seen=seen,
                records=records,
                depth=depth + 1,
            )
        return
    if isinstance(payload, str):
        _collect_from_text(
            payload,
            protocol=protocol,
            proxies=proxies,
            seen=seen,
            records=records,
        )


def _raise_no_proxy_error() -> None:
    raise ProxyApiError("代理 API 返回成功，但没有解析到代理 IP 和端口")


def parse_proxy_api_response(
    payload: Any,
    *,
    protocol: str,
    profile: ProxyApiProfile | str | None = None,
) -> list[str]:
    proxies, _records = _parse_proxy_payload(
        payload,
        protocol=protocol,
        profile=profile,
    )
    return proxies


def _parse_proxy_payload(
    payload: Any,
    *,
    protocol: str,
    profile: ProxyApiProfile | str | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    profile_obj = _coerce_profile(profile)
    _raise_if_provider_failure(payload, profile_obj)

    proxies: list[str] = []
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    _collect_from_payload(
        payload,
        protocol=normalize_proxy_api_protocol(protocol),
        proxies=proxies,
        seen=seen,
        records=records,
    )
    if not proxies:
        _raise_no_proxy_error()
    return proxies, records


def _load_json_payload(text: str) -> Any | None:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _xml_element_to_value(element: ElementTree.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()

    grouped: dict[str, list[Any]] = {}
    for child in children:
        grouped.setdefault(child.tag.lower(), []).append(_xml_element_to_value(child))

    result: dict[str, Any] = {}
    for key, values in grouped.items():
        result[key] = values[0] if len(values) == 1 else values
    return result


def _load_xml_payload(text: str) -> Any | None:
    raw = str(text or "").strip()
    if not raw.startswith("<"):
        return None
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError:
        return None
    return {root.tag.lower(): _xml_element_to_value(root)}


def parse_proxy_api_response_text(
    text: str,
    *,
    protocol: str,
    profile: ProxyApiProfile | str | None = None,
) -> list[str]:
    profile_obj = _coerce_profile(profile)
    payload = _load_json_payload(str(text or ""))
    if payload is not None:
        return parse_proxy_api_response(payload, protocol=protocol, profile=profile_obj)
    payload = _load_xml_payload(str(text or ""))
    if payload is not None:
        return parse_proxy_api_response(payload, protocol=protocol, profile=profile_obj)

    proxies: list[str] = []
    seen: set[str] = set()
    _collect_from_text(
        str(text or ""),
        protocol=normalize_proxy_api_protocol(protocol),
        proxies=proxies,
        seen=seen,
    )
    if not proxies:
        first_line = next(
            (line.strip() for line in str(text or "").splitlines() if line.strip()),
            "",
        )
        if first_line:
            raise ProxyApiError(
                f"代理 API 返回成功，但没有解析到代理 IP 和端口。原始返回: {first_line[:120]}"
            )
        _raise_no_proxy_error()
    return proxies


def fetch_proxy_api(
    api_url: str,
    *,
    count: int,
    protocol: str,
    timeout: int = 15,
) -> ProxyApiResult:
    request = build_proxy_api_request(api_url, count=count, protocol=protocol)
    response = requests.request(
        "GET", request.url, headers={}, data={}, timeout=timeout
    )
    response.raise_for_status()

    raw_text = response.text
    payload = _load_json_payload(raw_text)
    if payload is not None:
        proxies, records = _parse_proxy_payload(
            payload,
            protocol=protocol,
            profile=request.profile,
        )
        return ProxyApiResult(
            proxies=proxies,
            response=payload if isinstance(payload, dict) else {"data": payload},
            proxy_records=records,
        )

    payload = _load_xml_payload(raw_text)
    if payload is not None:
        proxies, records = _parse_proxy_payload(
            payload,
            protocol=protocol,
            profile=request.profile,
        )
        return ProxyApiResult(
            proxies=proxies,
            response=payload if isinstance(payload, dict) else {"data": payload},
            proxy_records=records,
        )

    proxies: list[str] = []
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    _collect_from_text(
        raw_text,
        protocol=normalize_proxy_api_protocol(protocol),
        proxies=proxies,
        seen=seen,
        records=records,
    )
    if not proxies:
        parse_proxy_api_response_text(
            raw_text,
            protocol=protocol,
            profile=request.profile,
        )
    return ProxyApiResult(
        proxies=proxies,
        response={"raw": raw_text},
        proxy_records=records,
    )
