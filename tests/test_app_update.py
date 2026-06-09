import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from app_update import (
    UPDATE_CHANNEL_PRERELEASE,
    UPDATE_CHANNEL_STABLE,
    ReleaseInfo,
    UpdateError,
    download_update_package,
    select_update,
)


def _release(tag, *, prerelease=False, draft=False, assets=None):
    return {
        "tag_name": tag,
        "name": tag,
        "html_url": f"https://example.test/{tag}",
        "body": "notes",
        "prerelease": prerelease,
        "draft": draft,
        "published_at": "2026-06-08T00:00:00Z",
        "assets": assets or [],
    }


def test_stable_channel_skips_prereleases():
    releases = [_release("v2.15.0-beta.1", prerelease=True), _release("v2.14.17")]
    update = select_update(releases, "2.14.16", UPDATE_CHANNEL_STABLE)
    assert update is not None
    assert update.version == "2.14.17"


def test_prerelease_channel_selects_newest_version():
    releases = [_release("v2.14.17"), _release("v2.15.0-beta.1", prerelease=True)]
    update = select_update(releases, "2.14.16", UPDATE_CHANNEL_PRERELEASE)
    assert update is not None
    assert update.version == "2.15.0b1"


class FakeResponse:
    def __init__(self, *, payload=None, content=b""):
        self._payload = payload
        self._content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self, manifest, package):
        self.manifest = manifest
        self.package = package

    def get(self, url, **kwargs):
        if url.endswith("version-info.json"):
            return FakeResponse(payload=self.manifest)
        return FakeResponse(content=self.package)


def test_download_verifies_sha256(tmp_path: Path):
    package = b"verified update"
    filename = "btb_linux_amd64_v2.14.17.zip"
    manifest = {
        "version": "v2.14.17",
        "files": {
            "linux_amd64": {
                "name": filename,
                "sha256": hashlib.sha256(package).hexdigest(),
                "size": len(package),
            }
        },
    }
    release = ReleaseInfo(
        version="2.14.17",
        tag_name="v2.14.17",
        name="v2.14.17",
        html_url="https://example.test/release",
        body="",
        prerelease=False,
        published_at="",
        assets=(
            {
                "name": "version-info.json",
                "browser_download_url": "https://example.test/version-info.json",
                "size": 1,
            },
            {
                "name": filename,
                "browser_download_url": "https://example.test/package.zip",
                "size": len(package),
            },
        ),
    )

    with patch("app_update.platform_asset_key", return_value="linux_amd64"):
        output = download_update_package(
            release, tmp_path, session=FakeSession(manifest, package)
        )

    assert output.read_bytes() == package


def test_download_rejects_bad_sha256(tmp_path: Path):
    filename = "btb_linux_amd64_v2.14.17.zip"
    manifest = {
        "version": "v2.14.17",
        "files": {
            "linux_amd64": {
                "name": filename,
                "sha256": "0" * 64,
                "size": len(b"tampered"),
            }
        },
    }
    release = ReleaseInfo(
        version="2.14.17",
        tag_name="v2.14.17",
        name="v2.14.17",
        html_url="https://example.test/release",
        body="",
        prerelease=False,
        published_at="",
        assets=(
            {
                "name": "version-info.json",
                "browser_download_url": "https://example.test/version-info.json",
                "size": 1,
            },
            {
                "name": filename,
                "browser_download_url": "https://example.test/package.zip",
                "size": len(b"tampered"),
            },
        ),
    )

    with patch("app_update.platform_asset_key", return_value="linux_amd64"):
        with pytest.raises(UpdateError, match="SHA-256"):
            download_update_package(
                release, tmp_path, session=FakeSession(manifest, b"tampered")
            )

    assert not list(tmp_path.iterdir())
