from __future__ import annotations

from tab import settings


class _JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeRequest:
    def get(self, url: str):
        if "linkgoods/list" in url:
            return _JsonResponse({"data": {"list": []}})
        if "buyer/list" in url:
            return _JsonResponse(
                {
                    "data": {
                        "list": [
                            {"name": "alice", "personal_id": "id-a"},
                        ]
                    }
                }
            )
        if "addr/list" in url:
            return _JsonResponse(
                {
                    "data": {
                        "addr_list": [
                            {
                                "addr": "road 1",
                                "area": "area",
                                "city": "city",
                                "id": 1,
                                "name": "receiver",
                                "phone": "13800138000",
                                "prov": "prov",
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"unexpected url: {url}")


class _FakeCookieManager:
    def __init__(self, uid: str):
        self.uid = uid

    def have_cookies(self):
        return True

    def get_cookies_value(self, name: str):
        if name == "DedeUserID":
            return self.uid
        return None


class _FakeAccountRequest:
    def __init__(self, uid: str):
        self.cookieManager = _FakeCookieManager(uid)


def _project_payload():
    return {
        "id": 123,
        "name": "demo project",
        "hotProject": False,
        "has_eticket": True,
        "sales_dates": [],
        "start_time": 1735689600,
        "end_time": 1735689600,
        "screen_list": [
            {
                "id": 10,
                "name": "day 1",
                "project_id": 123,
                "ticket_list": [
                    {
                        "desc": "vip",
                        "id": 20,
                        "price": 100,
                        "sale_start": "2026-01-01 12:00:00",
                    }
                ],
            }
        ],
    }


def test_submit_ticket_id_resets_stale_selection_values(monkeypatch):
    monkeypatch.setattr(settings.util, "main_request", _FakeRequest())
    monkeypatch.setattr(
        settings,
        "fetch_project_payload",
        lambda request, project_id: _project_payload(),
    )
    monkeypatch.setattr(
        settings,
        "_fetch_screens_by_date_with_fallback",
        lambda request, project_id, date_str: [],
    )

    updates = next(settings.on_submit_ticket_id("123"))

    assert updates[0]["value"] is None
    assert updates[1]["choices"] == ["alice-id-a"]
    assert updates[1]["value"] == []
    assert updates[2]["value"] is None


def test_submit_ticket_id_keeps_dates_when_account_data_is_unavailable(monkeypatch):
    class _AccountDataUnavailableRequest(_FakeRequest):
        def get(self, url: str):
            if "buyer/list" in url:
                raise RuntimeError("当前未登录")
            return super().get(url)

    project = _project_payload()
    project["sales_dates"] = [{"date": "2026-07-16"}]

    warnings = []
    monkeypatch.setattr(settings.util, "main_request", _AccountDataUnavailableRequest())
    monkeypatch.setattr(
        settings,
        "fetch_project_payload",
        lambda request, project_id: project,
    )
    monkeypatch.setattr(
        settings,
        "_fetch_screens_by_date_with_fallback",
        lambda request, project_id, date_str: [],
    )
    monkeypatch.setattr(
        settings.gr, "Warning", lambda message: warnings.append(message)
    )

    updates = next(settings.on_submit_ticket_id("123"))

    assert updates[0]["choices"]
    assert updates[1]["choices"] == []
    assert updates[2]["choices"] == []
    assert updates[5]["choices"] == ["2026-07-16"]
    assert updates[5]["value"] == "2026-07-16"
    assert warnings == [
        "票档和日期已获取；请先在“账号登录”页重新登录，以加载实名购票人和收货地址。"
    ]


def test_has_invalid_index_detects_stale_buyer_selection():
    assert not settings._has_invalid_index([0], [{"name": "alice"}])
    assert settings._has_invalid_index([0, 1], [{"name": "alice"}])


def test_submit_all_rejects_ticket_context_from_previous_account(monkeypatch):
    settings._reset_ticket_context()
    settings.ticket_context_account_uid = "old-uid"
    settings.buyer_value = [{"name": "alice", "personal_id": "id-a"}]
    settings.addr_value = [
        {
            "addr": "road 1",
            "area": "area",
            "city": "city",
            "id": 1,
            "name": "receiver",
            "phone": "13800138000",
            "prov": "prov",
        }
    ]
    settings.ticket_value = [
        {
            "project_id": 123,
            "ticket": {
                "screen_id": 10,
                "is_hot_project": False,
                "id": 20,
                "price": 100,
                "sale_start": "2026-01-01 12:00:00",
            },
        }
    ]
    settings.ticket_str_list = ["day 1 - vip"]

    warnings = []
    monkeypatch.setattr(settings.util, "main_request", _FakeAccountRequest("new-uid"))
    monkeypatch.setattr(
        settings.gr, "Warning", lambda message: warnings.append(message)
    )

    assert (
        list(
            settings.on_submit_all(
                "123",
                0,
                [0],
                "buyer",
                "13800138000",
                0,
            )
        )
        == []
    )
    assert warnings == ["当前账号已切换，请重新获取票务信息后再生成配置。"]
