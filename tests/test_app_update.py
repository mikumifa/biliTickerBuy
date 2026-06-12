from app_update import (
    UPDATE_CHANNEL_PRERELEASE,
    UPDATE_CHANNEL_STABLE,
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
