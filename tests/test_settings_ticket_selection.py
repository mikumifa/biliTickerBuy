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


def test_has_invalid_index_detects_stale_buyer_selection():
    assert not settings._has_invalid_index([0], [{"name": "alice"}])
    assert settings._has_invalid_index([0, 1], [{"name": "alice"}])
