import pytest

from util.proxy.ProxyManager import ProxyManager
from util.proxy.ProxyApiProvider import (
    ProxyApiError,
    build_proxy_api_request,
    build_proxy_api_url,
    detect_proxy_api_profile,
    fetch_proxy_api,
    mask_proxy_api_url,
    parse_proxy_api_response,
    parse_proxy_api_response_text,
)


def _proxy_url(scheme: str, username: str, password: str, host: str, port: int) -> str:
    return f"{scheme}://" + f"{username}:{password}@" + f"{host}:{port}"


def test_build_proxy_api_url_preserves_existing_provider_demo_params():
    original_url = (
        "https://dps.kdlapi.com/api/getdps/?client_id=demo"
        "&signed_value=a%2fb%2b%3d&num=7&format=text&sep=1"
    )
    url = build_proxy_api_url(
        original_url,
        count=3,
        protocol="socks5",
    )

    assert url == original_url


def test_build_proxy_api_url_fills_blank_known_params_only():
    url = build_proxy_api_url(
        "http://api.youdaili.com/v1/proxy/get?client_id=&count=&format=&protocol=",
        count=3,
        protocol="socks5",
    )

    assert url == (
        "http://api.youdaili.com/v1/proxy/get?client_id=&count=3&format=json&protocol=socks5"
    )


def test_detect_proxy_api_profile_by_common_provider_hosts():
    samples = {
        "http://api.youdaili.com/v1/proxy/get?count=1": "youdaili",
        "https://dps.kdlapi.com/api/getdps/?num=1": "kuaidaili",
        "https://webapi.http.zhimacangku.com/getip?num=1&type=2": "zhima",
        "https://api.xiaoxiangdaili.com/ip/get?cnt=1&wt=json": "xiaoxiang",
        "http://api.xiequ.cn/VAD/GetIp.aspx?num=1": "xiequ",
        "https://v2.api.juliangip.com/dynamic/getips?num=1": "juliang",
        "https://share.proxy.qg.net/get?num=1": "qingguo",
        "https://proxy.16yun.cn/api?num=1": "yiniuyun",
        "http://tiqu.pyhttp.taolop.com/getflowip?count=1": "pinyi",
        "https://taiyang.example.com/api?num=1": "taiyang",
        "https://mogumiao.example.com/proxy?num=1": "mogu",
        "https://xundaili.example.com/api?num=1": "xundaili",
        "https://www.zdaye.com/dayProxy/ip/123/demo?count=1": "zdaye",
        "https://proxy.example.com/api?qty=1": "generic",
    }

    for url, expected_profile in samples.items():
        assert detect_proxy_api_profile(url).name == expected_profile


def test_build_proxy_api_request_adds_profile_specific_missing_params():
    request = build_proxy_api_request(
        "https://api.xiaoxiangdaili.com/ip/get",
        count=6,
        protocol="http",
    )

    assert request.profile.name == "xiaoxiang"
    assert request.url == (
        "https://api.xiaoxiangdaili.com/ip/get?cnt=6&wt=json"
    )


def test_build_proxy_api_request_does_not_add_params_for_unknown_provider():
    request = build_proxy_api_request(
        "https://proxy.example.com/api?client_id=demo",
        count=6,
        protocol="socks5",
    )

    assert request.profile.name == "generic"
    assert request.url == "https://proxy.example.com/api?client_id=demo"


def test_parse_youdaili_success_response_as_http_proxy():
    payload = {
        "code": 0,
        "msg": "OK",
        "data": {
            "count": 1,
            "proxy_list": [
                {
                    "ip": "8.8.8.8",
                    "port": 12234,
                }
            ],
        },
    }

    assert parse_proxy_api_response(payload, protocol="http") == [
        "http://8.8.8.8:12234"
    ]


def test_parse_youdaili_success_response_as_socks_proxy():
    payload = {
        "code": 0,
        "msg": "OK",
        "data": {
            "proxy_list": [
                {
                    "ip": "8.8.8.8",
                    "port": 12234,
                }
            ],
        },
    }

    assert parse_proxy_api_response(payload, protocol="socks5") == [
        "socks5://8.8.8.8:12234"
    ]


def test_parse_proxy_api_keeps_auth_from_standard_url():
    proxy = _proxy_url("http", "proxy_user", "proxy_pass", "192.0.2.10", 15674)
    payload = {
        "code": 0,
        "data": [proxy],
    }

    assert parse_proxy_api_response(payload, protocol="http") == [proxy]


def test_parse_proxy_api_keeps_auth_from_host_port_user_pass():
    payload = {
        "code": 0,
        "proxies": [
            "192.0.2.20:15115:proxy_user:proxy_pass",
        ],
    }

    assert parse_proxy_api_response(payload, protocol="http") == [
        _proxy_url("http", "proxy_user", "proxy_pass", "192.0.2.20", 15115)
    ]


def test_parse_proxy_api_keeps_auth_from_object_fields():
    payload = {
        "code": 0,
        "data": [
            {
                "host": "192.0.2.30",
                "port": 15115,
                "Authkey": "proxy_user",
                "Authpwd": "proxy_pass",
                "protocol": "http",
            }
        ],
    }

    assert parse_proxy_api_response(payload, protocol="http") == [
        _proxy_url("http", "proxy_user", "proxy_pass", "192.0.2.30", 15115)
    ]


def test_parse_proxy_api_merges_auth_fields_with_proxy_field():
    payload = {
        "code": 0,
        "data": [
            {
                "proxy": "192.0.2.40:15115",
                "Username": "proxy_user",
                "Password": "proxy_pass",
                "protocol": "http",
            }
        ],
    }

    assert parse_proxy_api_response(payload, protocol="http") == [
        _proxy_url("http", "proxy_user", "proxy_pass", "192.0.2.40", 15115)
    ]


def test_parse_proxy_api_keeps_auth_for_socks5_url():
    proxy = _proxy_url("socks5", "user", "pass", "127.0.0.1", 1080)
    payload = {
        "code": 0,
        "data": [proxy],
    }

    assert parse_proxy_api_response(payload, protocol="socks5") == [proxy]


def test_parse_proxy_api_response_text_extracts_plain_lines():
    payload = """
    192.0.2.50:15115
    192.0.2.51:15116
    192.0.2.50:15115
    """

    assert parse_proxy_api_response_text(payload, protocol="http") == [
        "http://192.0.2.50:15115",
        "http://192.0.2.51:15116",
    ]


def test_parse_proxy_api_response_text_extracts_csv_like_rows():
    payload = "ip,port\n192.0.2.54,15119\n"

    assert parse_proxy_api_response_text(payload, protocol="http") == [
        "http://192.0.2.54:15119"
    ]


def test_parse_proxy_api_response_walks_nested_provider_payloads():
    payload = {
        "ERRORCODE": "0",
        "RESULT": {
            "rows": [
                {
                    "IP": "192.0.2.60",
                    "PORT": "15120",
                }
            ]
        },
    }

    assert parse_proxy_api_response(payload, protocol="http") == [
        "http://192.0.2.60:15120"
    ]


def test_parse_proxy_api_response_accepts_json_list_root():
    payload = [
        {"ip": "192.0.2.61", "port": 15121},
        "192.0.2.62:15122",
    ]

    assert parse_proxy_api_response(payload, protocol="socks5") == [
        "socks5://192.0.2.61:15121",
        "socks5://192.0.2.62:15122",
    ]


def test_parse_proxy_api_response_auto_defaults_bare_proxy_to_http():
    payload = {
        "code": 0,
        "data": [
            {"ip": "192.0.2.66", "port": 15126},
            "192.0.2.67:15127",
        ],
    }

    assert parse_proxy_api_response(payload, protocol="auto") == [
        "http://192.0.2.66:15126",
        "http://192.0.2.67:15127",
    ]


def test_parse_proxy_api_response_auto_keeps_explicit_proxy_scheme():
    payload = {
        "code": 0,
        "data": [
            "socks5://192.0.2.68:15128",
            "http://192.0.2.69:15129",
        ],
    }

    assert parse_proxy_api_response(payload, protocol="auto") == [
        "socks5://192.0.2.68:15128",
        "http://192.0.2.69:15129",
    ]


def test_parse_proxy_api_response_extracts_more_proxy_fields_and_ttl_metadata():
    payload = {
        "code": 0,
        "data": [
            {
                "server": "192.0.2.64:15124",
                "proxy_ip": "198.51.100.64",
                "deadline": "2026-07-07 12:30:00",
                "ttl": 120,
            }
        ],
    }

    assert parse_proxy_api_response(payload, protocol="http") == [
        "http://192.0.2.64:15124"
    ]


def test_parse_proxy_api_response_text_accepts_xml_payload():
    payload = """
    <root>
      <code>0</code>
      <data>
        <item>
          <ip>192.0.2.65</ip>
          <port>15125</port>
          <expire_time>2026-07-07 12:30:00</expire_time>
        </item>
      </data>
    </root>
    """

    assert parse_proxy_api_response_text(payload, protocol="socks5") == [
        "socks5://192.0.2.65:15125"
    ]


def test_parse_proxy_api_response_detects_provider_failure_codes():
    payload = {"ERRORCODE": "10055", "ERRORMSG": "提取数量不足"}

    with pytest.raises(ProxyApiError, match="提取数量不足"):
        parse_proxy_api_response(payload, protocol="http")


def test_parse_zdaye_success_code_10001_as_success():
    payload = {
        "code": "10001",
        "msg": "获取成功",
        "data": {
            "proxy_list": [
                {"ip": "192.0.2.63", "port": 15123},
            ],
        },
    }

    assert parse_proxy_api_response(payload, protocol="http", profile="zdaye") == [
        "http://192.0.2.63:15123"
    ]


def test_fetch_proxy_api_parses_text_response(monkeypatch):
    class Response:
        text = "192.0.2.70:15130\n192.0.2.71:15131"

        def raise_for_status(self):
            return None

    captured = {}

    def fake_request(method, url, headers, data, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("util.proxy.ProxyApiProvider.requests.request", fake_request)

    result = fetch_proxy_api(
        "https://dps.kdlapi.com/api/getdps/?num=2&format=text",
        count=9,
        protocol="http",
        timeout=3,
    )

    assert captured == {
        "method": "GET",
        "url": "https://dps.kdlapi.com/api/getdps/?num=2&format=text",
        "timeout": 3,
    }
    assert result.proxies == [
        "http://192.0.2.70:15130",
        "http://192.0.2.71:15131",
    ]
    assert result.response == {"raw": Response.text}


def test_fetch_proxy_api_result_can_replace_proxy_manager_pool(monkeypatch):
    class Response:
        text = "192.0.2.80:15140\n192.0.2.80:15140\n"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "util.proxy.ProxyApiProvider.requests.request",
        lambda method, url, headers, data, timeout: Response(),
    )

    manager = ProxyManager("none")
    result = fetch_proxy_api(
        "http://api.youdaili.com/v1/proxy/get?count=1&format=text",
        count=1,
        protocol="http",
    )
    manager.replace_proxy_list(",".join(result.proxies))

    assert manager.proxy_list == ["http://192.0.2.80:15140"]
    assert result.proxy_records == [
        {
            "proxy": "http://192.0.2.80:15140",
            "host": "192.0.2.80",
            "port": "15140",
            "scheme": "http",
        }
    ]


def test_mask_proxy_api_url_redacts_sensitive_query_values():
    assert mask_proxy_api_url(
        "https://example.com/get?key=&token=&num=2&signature="
    ) == "https://example.com/get?key=***&token=***&num=2&signature=***"


def test_parse_youdaili_failure_response_raises():
    payload = {
        "code": 104,
        "msg": "未检索到满足要求的代理IP，请调整筛选条件后再试，或联系客服处理！",
        "data": None,
    }

    with pytest.raises(ProxyApiError):
        parse_proxy_api_response(payload, protocol="http")
