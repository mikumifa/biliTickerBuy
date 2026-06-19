from task.buy import _extract_prepare_token


def test_extract_prepare_token_returns_none_when_missing():
    assert _extract_prepare_token(None) is None
    assert _extract_prepare_token({}) is None
    assert _extract_prepare_token({"data": None}) is None
    assert _extract_prepare_token({"data": {}}) is None
    assert _extract_prepare_token({"data": {"token": None}}) is None
    assert _extract_prepare_token({"data": {"token": "   "}}) is None


def test_extract_prepare_token_returns_string_when_present():
    assert _extract_prepare_token({"data": {"token": "abc"}}) == "abc"
    assert _extract_prepare_token({"data": {"token": "  abc  "}}) == "abc"
