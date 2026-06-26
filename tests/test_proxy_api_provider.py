import pytest

from util.proxy.ProxyApiProvider import (
    ProxyApiError,
    build_proxy_api_url,
    parse_proxy_api_response,
)


def test_build_proxy_api_url_overrides_required_params():
    url = build_proxy_api_url(
        "http://api.example.com/get?app_key=abc&count=&format=text&protocol=http",
        count=3,
        protocol="socks5",
    )

    assert url == (
        "http://api.example.com/get?app_key=abc&count=3&format=json&protocol=socks5"
    )


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
        "socks://8.8.8.8:12234"
    ]


def test_parse_youdaili_failure_response_raises():
    payload = {
        "code": 104,
        "msg": "未检索到满足要求的代理IP，请调整筛选条件后再试，或联系客服处理！",
        "data": None,
    }

    with pytest.raises(ProxyApiError):
        parse_proxy_api_response(payload, protocol="http")
