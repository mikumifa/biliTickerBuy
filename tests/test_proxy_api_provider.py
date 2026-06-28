import pytest

from util.proxy.ProxyApiProvider import (
    ProxyApiError,
    build_proxy_api_url,
    parse_proxy_api_response,
)


def _proxy_url(scheme: str, username: str, password: str, host: str, port: int) -> str:
    return f"{scheme}://" + f"{username}:{password}@" + f"{host}:{port}"


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


def test_parse_youdaili_failure_response_raises():
    payload = {
        "code": 104,
        "msg": "未检索到满足要求的代理IP，请调整筛选条件后再试，或联系客服处理！",
        "data": None,
    }

    with pytest.raises(ProxyApiError):
        parse_proxy_api_response(payload, protocol="http")
