"""Regression fixture from Chongqing Mengxiang's public linkgoods API."""

import copy
import json
from types import SimpleNamespace
from pathlib import Path

from interface import project
from tab import settings


SCREEN = {
    "id": 1024355,
    "name": "2026/10/03  9:00—17:00",
    "start_time": 1790989200,
    "sale_start": 1788080400,
    "ticket_list": [
        {
            "id": 932296,
            "price": 990,
            "desc": "纸老虎签售票",
            "sale_start": "Sun Aug 30 17:00:00 CST 2026",
            "sale_flag_number": 4,
        }
    ],
}


class Response:
    def __init__(self, data):
        self.data = data

    def json(self):
        return copy.deepcopy(self.data)


class Request:
    def get(self, url):
        if "linkgoods/list" in url:
            return Response({"errno": 0, "data": {"list": [{"id": 1}, {"id": 3049}]}})
        if "link_id=1" in url:
            raise RuntimeError("one removed merchandise entry")
        if "link_id=3049" in url:
            return Response(
                {
                    "errno": 0,
                    "data": {
                        "item_id": 1005095,
                        "specs_list": [SCREEN],
                    },
                }
            )
        if "infoByDate" in url:
            return Response({"errno": 0, "data": {"screen_list": []}})
        raise AssertionError(url)


def test_one_bad_entry_does_not_hide_guests_and_sale_time_is_normalized():
    screens = project._merge_link_goods(
        request=Request(), screen_list=[], project_id=1004484
    )
    assert len(screens) == 1
    assert screens[0]["project_id"] == 1005095
    assert screens[0]["link_id"] == 3049
    assert screens[0]["ticket_list"][0]["sale_start"] == "2026-08-30 17:00:00"
    assert SCREEN["ticket_list"][0]["sale_start"] == "Sun Aug 30 17:00:00 CST 2026"


def test_date_refresh_includes_matching_guest_even_without_general_tickets(monkeypatch):
    monkeypatch.setattr(
        settings, "_fetch_screens_by_date_with_fallback", lambda *args: []
    )
    screens = settings._fetch_date_screens_with_link_goods(
        Request(), 1004484, "2026-10-03"
    )
    assert len(screens) == 1
    assert screens[0]["project_id"] == 1005095
    assert (
        settings._fetch_date_screens_with_link_goods(Request(), 1004484, "2026-10-02")
        == []
    )


def test_interface_date_selection_retains_child_project_and_link():
    payload = {
        "id": 1004484,
        "hotProject": False,
        "has_eticket": True,
        "screen_list": [],
    }
    options = project._fetch_ticket_options(
        request=Request(), project_payload=payload, selected_date="2026-10-03"
    )
    assert len(options) == 1
    ticket = options[0]
    assert (
        ticket["project_id"],
        ticket["screen_id"],
        ticket["id"],
        ticket["link_id"],
    ) == (1005095, 1024355, 932296, 3049)
    assert ticket["price"] == 990
    assert ticket["sale_status"] == "售罄"
    assert (
        project._fetch_ticket_options(
            request=Request(), project_payload=payload, selected_date="2026-10-02"
        )
        == []
    )


def test_missing_sale_start_uses_beijing_screen_timestamp():
    assert project._normalize_link_sale_start({}, SCREEN) == "2026-08-30 17:00:00"


def test_web_config_generation_preserves_guest_ids_and_time(monkeypatch, tmp_path):
    settings._reset_ticket_context()
    payload = {"id": 1004484, "hotProject": False, "has_eticket": True}
    option = project._fetch_ticket_options(
        request=Request(),
        project_payload=payload,
        selected_date="2026-10-03",
    )[0]
    monkeypatch.setattr(
        settings,
        "ticket_value",
        [{"project_id": option["project_id"], "ticket": option}],
    )
    monkeypatch.setattr(settings, "ticket_str_list", [option["display"]])
    monkeypatch.setattr(
        settings, "buyer_value", [{"name": "TEST", "personal_id": "TEST-ONLY"}]
    )
    monkeypatch.setattr(
        settings,
        "addr_value",
        [
            {
                "name": "TEST",
                "phone": "000",
                "id": 1,
                "prov": "",
                "city": "",
                "area": "",
                "addr": "TEST",
            }
        ],
    )
    monkeypatch.setattr(settings, "TEMP_PATH", str(tmp_path))
    monkeypatch.setattr(settings.ConfigDB, "insert", lambda *args: None)
    cookie_manager = SimpleNamespace(
        get_cookies=lambda: [{"name": "test", "value": "fake"}],
        get_config_value=lambda *args: "",
    )
    monkeypatch.setattr(
        settings.util,
        "main_request",
        SimpleNamespace(
            get_request_name=lambda: "TEST",
            cookieManager=cookie_manager,
        ),
    )
    updates = next(settings.on_submit_all("1004484", 0, [0], "TEST", "000", 0))
    config = json.loads(Path(updates[1]["value"]).read_text(encoding="utf-8"))
    assert (
        config["project_id"],
        config["screen_id"],
        config["sku_id"],
        config["link_id"],
    ) == (1005095, 1024355, 932296, 3049)
    assert config["sale_start"] == "2026-08-30 17:00:00"
    assert config["pay_money"] == 990


def test_all_dates_keeps_guest_options(monkeypatch):
    monkeypatch.setattr(
        settings,
        "fetch_project_payload",
        lambda **kwargs: {
            "screen_list": [],
            "start_time": 1790989200,
            "end_time": 1790989200,
        },
    )
    monkeypatch.setattr(
        settings, "_fetch_screens_by_date_with_fallback", lambda *args: []
    )
    assert (
        settings._fetch_date_screens_with_link_goods(Request(), 1004484, "全部日期")[0][
            "link_id"
        ]
        == 3049
    )


def test_guest_config_reaches_order_payload_without_parent_id_substitution(monkeypatch):
    from task import buy_helpers
    from tab.go import _parse_sale_start

    config = {
        "project_id": 1005095,
        "screen_id": 1024355,
        "sku_id": 932296,
        "link_id": 3049,
        "count": 1,
        "pay_money": 990,
        "sale_start": "2026-08-30 17:00:00",
        "buyer_info": [],
    }
    assert _parse_sale_start(config["sale_start"]).hour == 17
    assert buy_helpers.build_token_payload(config)["project_id"] == 1005095
    monkeypatch.setattr(
        buy_helpers,
        "sim_ctoken_state",
        lambda **kwargs: SimpleNamespace(generate_create_ctoken=lambda: "TEST"),
    )
    url, payload = buy_helpers.prepare_create_request(config, "TEST", False, None, None)
    assert "project_id=1005095" in url
    assert payload["link_id"] == 3049
    assert payload["sku_id"] == 932296
    # Only construct the payload: no request is sent.
