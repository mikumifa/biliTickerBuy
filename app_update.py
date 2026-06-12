"""GitHub release discovery for update notifications."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import requests
from packaging.version import InvalidVersion, Version

GITHUB_REPOSITORY = "mikumifa/biliTickerBuy"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases"
UPDATE_CHANNEL_STABLE = "稳定版"
UPDATE_CHANNEL_PRERELEASE = "测试版"
UPDATE_CHANNELS = (UPDATE_CHANNEL_STABLE, UPDATE_CHANNEL_PRERELEASE)
REQUEST_TIMEOUT = (5, 20)


class UpdateError(RuntimeError):
    """Raised when an update cannot be discovered or downloaded safely."""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag_name: str
    name: str
    html_url: str
    body: str
    prerelease: bool
    published_at: str
    assets: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["assets"] = list(self.assets)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReleaseInfo":
        return cls(
            version=str(data["version"]),
            tag_name=str(data["tag_name"]),
            name=str(data.get("name") or data["tag_name"]),
            html_url=str(data["html_url"]),
            body=str(data.get("body") or ""),
            prerelease=bool(data.get("prerelease")),
            published_at=str(data.get("published_at") or ""),
            assets=tuple(data.get("assets") or ()),
        )


def normalize_version(value: str) -> Version:
    candidate = value.strip()
    if candidate.lower().startswith("v"):
        candidate = candidate[1:]
    try:
        return Version(candidate)
    except InvalidVersion as exc:
        raise UpdateError(f"无法识别版本号：{value}") from exc


def select_update(
    releases: Iterable[dict[str, Any]], current_version: str, channel: str
) -> ReleaseInfo | None:
    if channel not in UPDATE_CHANNELS:
        raise UpdateError(f"未知更新频道：{channel}")

    current = normalize_version(current_version)
    candidates: list[tuple[Version, dict[str, Any]]] = []
    for release in releases:
        if release.get("draft"):
            continue
        try:
            release_version = normalize_version(str(release.get("tag_name", "")))
        except UpdateError:
            continue
        is_prerelease = bool(release.get("prerelease")) or release_version.is_prerelease
        if channel == UPDATE_CHANNEL_STABLE and is_prerelease:
            continue
        if release_version > current:
            candidates.append((release_version, release))

    if not candidates:
        return None

    version, release = max(candidates, key=lambda item: item[0])
    assets = tuple(
        {
            "name": str(asset.get("name") or ""),
            "browser_download_url": str(asset.get("browser_download_url") or ""),
            "size": int(asset.get("size") or 0),
        }
        for asset in release.get("assets") or ()
        if asset.get("name") and asset.get("browser_download_url")
    )
    return ReleaseInfo(
        version=str(version),
        tag_name=str(release.get("tag_name") or version),
        name=str(release.get("name") or release.get("tag_name") or version),
        html_url=str(release.get("html_url") or ""),
        body=str(release.get("body") or ""),
        prerelease=bool(release.get("prerelease")) or version.is_prerelease,
        published_at=str(release.get("published_at") or ""),
        assets=assets,
    )


def fetch_update(
    current_version: str,
    channel: str,
    *,
    session: requests.Session | None = None,
) -> ReleaseInfo | None:
    client = session or requests.Session()
    response = client.get(
        GITHUB_RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"biliTickerBuy/{current_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise UpdateError("GitHub 返回了无法识别的版本列表。")
    return select_update(payload, current_version, channel)
