from interface import common, project


class _JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeRequest:
    def __init__(self, payload):
        self.headers = {
            "origin": "https://show.bilibili.com",
            "referer": "https://show.bilibili.com/",
        }
        self.payload = payload
        self.post_calls = []

    def post(self, *, url, data, isJson):
        self.post_calls.append((url, data, isJson, dict(self.headers)))
        return _JsonResponse(self.payload)

    def get(self, url):
        assert "linkgoods/list" in url
        return _JsonResponse({"data": {"list": []}})


def _ticket_renovation_payload():
    return {
        "code": 0,
        "success": True,
        "data": {
            "projectId": 1003217,
            "projectName": "新版票务活动",
            "hotProject": True,
            "endTime": 1760000000000,
            "salesDates": [{"dateStr": "2026-10-09", "week": "周五"}],
            "skuVenueInfo": {
                "venueName": "测试场馆",
                "addressDetail": "测试路 1 号",
            },
            "screenList": [
                {
                    "screenId": 345,
                    "screenName": "2026-10-09 19:00",
                    "startTime": 1760000000000,
                    "expressFee": 0,
                    "ticketList": [
                        {
                            "skuId": 456,
                            "skuName": "VIP 票",
                            "price": 12800,
                            "saleStart": "2026-08-01 12:00:00",
                            "saleFlagNumber": 101,
                            "canClick": False,
                        }
                    ],
                }
            ],
        },
    }


def test_ticket_renovation_link_extracts_project_id():
    assert (
        common._extract_project_id(
            "https://mall.bilibili.com/neul-next/ticket-renovation/detail.html"
            "?bilibiliappTest=&id=1003217"
        )
        == 1003217
    )


def test_new_ticket_renovation_payload_normalizes_camel_case_ticket_fields():
    request = _FakeRequest(_ticket_renovation_payload())

    payload = project._fetch_project_payload_new(
        request=request,
        project_id=1003217,
    )

    assert request.headers == {
        "origin": "https://show.bilibili.com",
        "referer": "https://show.bilibili.com/",
    }
    assert request.post_calls == [
        (
            project.NEW_PROJECT_DETAIL_URL,
            {"itemsId": 1003217, "itemsDetailPageType": 3},
            True,
            {
                "origin": "https://mall.bilibili.com",
                "referer": (
                    "https://mall.bilibili.com/neul-next/ticket-renovation/detail.html"
                    "?bilibiliappTest=&id=1003217"
                ),
            },
        )
    ]
    assert payload["name"] == "新版票务活动"
    assert payload["sales_dates"] == [
        {"dateStr": "2026-10-09", "week": "周五", "date": "2026-10-09"}
    ]
    assert payload["venue_info"] == {
        "venueName": "测试场馆",
        "addressDetail": "测试路 1 号",
        "name": "测试场馆",
        "address_detail": "测试路 1 号",
    }
    assert payload["start_time"] == 1760000000
    assert payload["end_time"] == 1760000000
    assert payload["screen_list"] == [
        {
            "screenId": 345,
            "screenName": "2026-10-09 19:00",
            "startTime": 1760000000000,
            "expressFee": 0,
            "ticketList": [
                {
                    "skuId": 456,
                    "skuName": "VIP 票",
                    "price": 12800,
                    "saleStart": "2026-08-01 12:00:00",
                    "saleFlagNumber": 101,
                    "canClick": False,
                }
            ],
            "id": 345,
            "name": "2026-10-09 19:00",
            "project_id": 1003217,
            "express_fee": 0,
            "start_time": 1760000000,
            "start_time_str": "",
            "ticket_list": [
                {
                    "skuId": 456,
                    "skuName": "VIP 票",
                    "price": 12800,
                    "saleStart": "2026-08-01 12:00:00",
                    "saleFlagNumber": 101,
                    "canClick": False,
                    "id": 456,
                    "desc": "VIP 票",
                    "sale_start": "2026-08-01 12:00:00",
                    "project_id": 1003217,
                    "screen_id": 345,
                    "screen_name": "2026-10-09 19:00",
                    "sale_flag_number": 101,
                    "clickable": False,
                }
            ],
        }
    ]


def test_new_ticket_renovation_ticket_list_produces_order_option():
    request = _FakeRequest(_ticket_renovation_payload())
    payload = project._fetch_project_payload_new(
        request=request,
        project_id=1003217,
    )

    options = project._fetch_ticket_options(
        request=request,
        project_payload=payload,
        selected_date=None,
    )

    assert len(options) == 1
    option = options[0]
    assert option["id"] == 456
    assert option["project_id"] == 1003217
    assert option["screen_id"] == 345
    assert option["price"] == 12800
    assert option["sale_status"] == "未开始"
    assert option["display"] == (
        "2026-10-09 19:00 - VIP 票 - ￥128.0 - 未开始 - "
        "【起售时间：2026-08-01 12:00:00】"
    )
