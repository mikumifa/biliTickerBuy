import pytest

from app_cmd.config.BwsConfig import BwsConfig
import interface.bws as bws
from interface.bws import (
    DEFAULT_BWS_RESERVE_DATES,
    _extract_act_days,
    _extract_bws_year_param,
    _extract_event_year,
    infer_bws_reserve_dates,
    resolve_bws_reserve_dates,
    verify_bws_ticket_activation,
)
from task.bws import Bws


def _reservation_info():
    return {
        "user_ticket_info": {
            "20260710": {
                "ticket": "TICKET-0710",
                "screen_name": "BW2026",
                "sku_name": "单日票",
            }
        },
        "user_reserve_info": {"20260710": []},
        "reserve_list": {
            "20260710": [
                {
                    "reserve_id": 1001,
                    "act_title": "签售项目",
                    "act_begin_time": 1783652400,
                    "reserve_begin_time": 1783648800,
                }
            ],
            "20260711": [
                {
                    "reserve_id": 1002,
                    "act_title": "舞台项目",
                    "act_begin_time": 1783738800,
                    "reserve_begin_time": 1783735200,
                }
            ],
        },
    }


def test_verify_bws_ticket_activation_uses_matching_activity_date():
    result = verify_bws_ticket_activation(_reservation_info(), reserve_id=1001)

    assert result["date"] == "20260710"
    assert result["ticket_no"] == "TICKET-0710"
    assert result["activity"]["reserve_id"] == 1001


def test_verify_bws_ticket_activation_fails_when_date_not_activated():
    with pytest.raises(RuntimeError, match="没有激活目标预约日期"):
        verify_bws_ticket_activation(_reservation_info(), reserve_id=1002)


def test_verify_bws_ticket_activation_fails_when_activity_missing():
    with pytest.raises(RuntimeError, match="未找到预约项目"):
        verify_bws_ticket_activation(_reservation_info(), reserve_id=9999)


def test_verify_bws_ticket_activation_allows_explicit_date_override():
    result = verify_bws_ticket_activation(
        _reservation_info(),
        reserve_id=1002,
        reserve_date="2026-07-10",
    )

    assert result["date"] == "20260710"
    assert result["ticket_no"] == "TICKET-0710"


def test_infer_bws_reserve_dates_uses_year_prefix():
    dates = infer_bws_reserve_dates("202601").split(",")

    assert dates[0] == "20260710"
    assert dates[-1] == "20260712"
    assert len(dates) == 3


def test_infer_bws_reserve_dates_supports_2025_demo_dates():
    assert infer_bws_reserve_dates("202501") == "20250711,20250712,20250713"


def test_resolve_bws_reserve_dates_defaults_to_starsbon_dates():
    assert resolve_bws_reserve_dates("", "202601") == DEFAULT_BWS_RESERVE_DATES


def test_resolve_bws_reserve_dates_keeps_manual_value():
    assert resolve_bws_reserve_dates("20260710,20260711", "202601") == (
        "20260710,20260711"
    )


def test_extract_official_bws_schedule_parts_from_minified_js():
    sample = (
        '<title>BW2026，次元新航线！</title>'
        'var c=e.isPre?202602:202601,l=e.isPre?202602:202601;'
        'e.ACT_DAYS=["20260710","20260711","20260712"];'
    )

    assert _extract_event_year(sample) == 2026
    assert _extract_bws_year_param(sample, 2026) == "202601"
    assert _extract_act_days(sample) == ["20260710", "20260711", "20260712"]


def test_bws_reserve_stream_stops_when_already_reserved(monkeypatch):
    class FakeClient:
        cookies = [{"name": "bili_jct", "value": "csrf"}]

        def get_username(self):
            return "tester"

        def get_reservation_info(self, **kwargs):
            return _reservation_info()

        def get_my_reservations(self, **kwargs):
            return {"reserve_list": {"20260710": [{"reserve_id": 1001}]}}

        def make_reservation(self, **kwargs):
            raise AssertionError("should not submit duplicate reservation")

    monkeypatch.setattr(bws, "_make_bws_client", lambda **kwargs: FakeClient())

    logs = list(
        bws.bws_reserve_stream(
            BwsConfig(
                reserve_id=1001,
                reserve_dates="20260710",
                retry_limit=1,
            )
        )
    )

    assert any("已在当前账号的预约列表中" in message for message in logs)


def test_bws_terminal_task_uses_bws_subcommand():
    args = Bws(
        BwsConfig(
            reserve_id=1001,
            reserve_dates="20260710",
            reserve_date="20260710",
            reserve_type=-1,
            year="202601",
            interval=300,
            retry_limit=2,
            cookies_path="cookies.json",
        )
    ).to_cli_args()

    assert args[0] == "bws"
    assert args[args.index("--reserve-id") + 1] == "1001"
    assert args[args.index("--reserve-date") + 1] == "20260710"
    assert args[args.index("--year") + 1] == "202601"
    assert args[args.index("--cookies-path") + 1] == "cookies.json"
