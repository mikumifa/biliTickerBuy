from __future__ import annotations

from task.buy_helpers import wait_until_start
from task.page_gate import (
    check_ticket_page_availability,
    normalize_mobile_ticket_page_url,
)
from app_cmd.config.BuyConfig import BuyConfig


TEST_MOBILE_URL = (
    "https://mall.bilibili.com/neul-next/ticket-renovation/detail.html?id=1002606"
)


class _FakeResponse:
    def __init__(self, text: str = "", payload=None):
        self.text = text
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, text: str, payload=None):
        self.text = text
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResponse(self.text)

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeResponse(payload=self.payload)


class _FakeCookieManager:
    def get_cookies(self, *, force: bool):
        assert force is True
        return [{"name": "SESSDATA", "value": "session-cookie"}]


class _FakeRequest:
    def __init__(self, text: str, payload=None):
        self.session = _FakeSession(text, payload)
        self.headers = {"user-agent": "desktop"}
        self.cookieManager = _FakeCookieManager()


def test_normalize_given_mobile_ticket_link_removes_tracking_parameters():
    source = (
        "https://mall.bilibili.com/neul-next/ticket-renovation/detail.html"
        "?from=newhomepage&id=1002606&msource=bilibiliapp&share_source=WEIXIN"
        "#themeType=2"
    )
    assert normalize_mobile_ticket_page_url(source) == TEST_MOBILE_URL


def test_normalize_desktop_ticket_link_to_mobile_page():
    source = "https://show.bilibili.com/platform/detail.html?id=1002606"
    assert normalize_mobile_ticket_page_url(source) == TEST_MOBILE_URL


def test_page_check_uses_mobile_page_and_detects_immediate_buy_button():
    request = _FakeRequest("<button>立即购买</button>")

    result = check_ticket_page_availability(
        request,
        "https://show.bilibili.com/platform/detail.html?id=1002606",
    )

    assert result.ready is True
    assert result.matched_text == "立即购买"
    url, kwargs = request.session.calls[0]
    assert url == TEST_MOBILE_URL
    assert kwargs["headers"]["user-agent"] != "desktop"
    assert kwargs["cookies"] == {"SESSDATA": "session-cookie"}


def test_page_check_uses_mobile_page_state_when_html_is_a_client_shell():
    request = _FakeRequest(
        "<div id=app></div>",
        {"data": {"canClick": True, "isSale": 1}},
    )

    result = check_ticket_page_availability(request, TEST_MOBILE_URL)

    assert result.ready is True
    assert result.matched_text == "立即购票（页面状态）"
    state_url, state_kwargs = request.session.calls[1]
    assert state_url.endswith("/mall-search-items/items_detail/info")
    assert state_kwargs["json"] == {"itemsId": 1002606, "itemsDetailPageType": 3}


def test_no_start_time_waits_for_the_button_before_returning(monkeypatch):
    responses = iter([False, True])
    monkeypatch.setattr("task.buy_helpers.time.sleep", lambda _seconds: None)

    events = list(
        wait_until_start(
            "",
            page_status_check=lambda: next(responses),
            page_timeout_seconds=10,
            page_poll_interval_seconds=0.1,
        )
    )

    assert not any(event.get("page_gate_timeout") for event in events)
    assert any("检测到" in str(event.get("message")) for event in events)


def test_page_gate_timeout_prevents_the_buy_flow_from_continuing(monkeypatch):
    class _AdvancingPerfCounter:
        def __init__(self):
            self.value = -0.6

        def __call__(self):
            self.value += 0.6
            return self.value

    monkeypatch.setattr("task.buy_helpers.time.perf_counter", _AdvancingPerfCounter())
    monkeypatch.setattr("task.buy_helpers.time.sleep", lambda _seconds: None)

    events = list(
        wait_until_start(
            "",
            page_status_check=lambda: False,
            page_timeout_seconds=1,
            page_poll_interval_seconds=0.1,
        )
    )

    assert any(event.get("page_gate_timeout") for event in events)


def test_page_gate_settings_are_loaded_and_forwarded_to_cli():
    config = BuyConfig.from_mapping(
        {
            "waitForBuyButton": True,
            "buyPageUrl": "https://show.bilibili.com/platform/detail.html?id=1002606",
            "buyPageTimeoutSeconds": 75,
            "buyPageCheckBeforeSeconds": 8,
        },
        source_name="db",
    )

    assert config.wait_for_buy_button is True
    assert config.buy_page_timeout_seconds == 75
    assert config.buy_page_check_before_seconds == 8
    args = config.to_cli_args()
    assert "--wait-for-buy-button" in args
    assert args[args.index("--buy-page-url") + 1] == (
        "https://show.bilibili.com/platform/detail.html?id=1002606"
    )
    assert args[args.index("--buy-page-timeout-seconds") + 1] == "75"
    assert args[args.index("--buy-page-check-before-seconds") + 1] == "8"
