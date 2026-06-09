"""GitHub release discovery and verified update-package downloads."""

from __future__ import annotations

import hashlib
import os
import platform
import re
from dataclasses import asdict, dataclass
from pathlib import Path
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


def platform_asset_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows" and machine in {"amd64", "x86_64"}:
        return "windows_amd64"
    if system == "linux" and machine in {"amd64", "x86_64"}:
        return "linux_amd64"
    if system == "linux" and machine in {"arm64", "aarch64"}:
        return "linux_arm64"
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "macos_arm64"
    if system == "darwin" and machine in {"amd64", "x86_64"}:
        return "macos_intel"
    raise UpdateError(f"当前平台暂不支持自动下载：{system}/{machine}")


def _find_asset(release: ReleaseInfo, name: str) -> dict[str, Any]:
    for asset in release.assets:
        if asset.get("name") == name:
            return asset
    raise UpdateError(f"GitHub Release 中缺少文件：{name}")


def _download_json(
    url: str, *, session: requests.Session, user_agent: str
) -> dict[str, Any]:
    response = session.get(
        url,
        headers={"Accept": "application/octet-stream", "User-Agent": user_agent},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise UpdateError("版本校验清单格式错误。")
    return payload


def download_update_package(
    release: ReleaseInfo,
    destination: str | os.PathLike[str],
    *,
    session: requests.Session | None = None,
) -> Path:
    client = session or requests.Session()
    user_agent = f"biliTickerBuy/{release.version}"
    manifest_asset = _find_asset(release, "version-info.json")
    manifest = _download_json(
        str(manifest_asset["browser_download_url"]),
        session=client,
        user_agent=user_agent,
    )

    manifest_version = str(manifest.get("version") or "")
    if normalize_version(manifest_version) != normalize_version(release.tag_name):
        raise UpdateError("版本校验清单与 GitHub Release 版本不一致。")

    key = platform_asset_key()
    file_info = (manifest.get("files") or {}).get(key)
    if not isinstance(file_info, dict):
        raise UpdateError(f"版本校验清单中缺少当前平台：{key}")

    filename = str(file_info.get("name") or "")
    expected_sha256 = str(file_info.get("sha256") or "").lower()
    if not filename or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise UpdateError("版本校验清单缺少有效的文件名或 SHA-256。")

    package_asset = _find_asset(release, filename)
    expected_size = int(file_info.get("size") or 0)
    if expected_size and int(package_asset.get("size") or 0) not in {0, expected_size}:
        raise UpdateError("版本校验清单中的文件大小与 GitHub Release 不一致。")

    destination_path = Path(destination).expanduser().resolve()
    destination_path.mkdir(parents=True, exist_ok=True)
    output_path = destination_path / Path(filename).name
    partial_path = output_path.with_suffix(output_path.suffix + ".part")

    digest = hashlib.sha256()
    try:
        with client.get(
            str(package_asset["browser_download_url"]),
            headers={"Accept": "application/octet-stream", "User-Agent": user_agent},
            timeout=REQUEST_TIMEOUT,
            stream=True,
        ) as response:
            response.raise_for_status()
            with partial_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
                        digest.update(chunk)
        if expected_size and partial_path.stat().st_size != expected_size:
            raise UpdateError("更新包大小校验失败，文件可能不完整，已取消更新。")
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            raise UpdateError("更新包 SHA-256 校验失败，文件可能不完整，已取消更新。")
        partial_path.replace(output_path)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    return output_path
