from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
from collections.abc import Sequence

try:
    from .h2connection import AddressFamily
    from .ja_h2_client import SourceAddress
except ImportError:  # pragma: no cover - supports direct import from util/h2client.
    from h2connection import AddressFamily
    from ja_h2_client import SourceAddress


H2CLIENT_SOURCE_INTERFACE_ALIASES = ("WLAN", "以太网")


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
