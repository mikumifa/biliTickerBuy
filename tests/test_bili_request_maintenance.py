from util.request.BiliRequest import BiliRequest


def test_handle_100001_calls_registered_handler():
    request = BiliRequest(cookies=[])
    calls = {"count": 0}

    def fake_handler():
        calls["count"] += 1

    request.set_100001_handler(fake_handler)

    assert request.handle_100001(100001) is True
    assert calls["count"] == 1


def test_handle_100001_ignores_other_errno():
    request = BiliRequest(cookies=[])
    calls = {"count": 0}

    def fake_handler():
        calls["count"] += 1

    request.set_100001_handler(fake_handler)

    assert request.handle_100001(0) is False
    assert calls["count"] == 0
