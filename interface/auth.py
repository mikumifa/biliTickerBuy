from __future__ import annotations

import tempfile
import time
from pathlib import Path

import requests

from .common import (
    _cookie_store_path,
    _fetch_username_silently,
    _make_request,
    _resolve_cookie_list,
)


def get_login_state(
    *,
    cookies: list[dict[str, object]] | dict[str, object] | None = None,
    cookies_path: str | Path | None = None,
) -> dict[str, object]:
    cookie_list = _resolve_cookie_list(cookies, cookies_path=cookies_path)
    has_cookies = bool(cookie_list)
    username = _fetch_username_silently(cookie_list)
    logged_in = has_cookies and username != "Not login"
    return {
        "ok": True,
        "logged_in": logged_in,
        "username": username,
        "has_cookies": has_cookies,
        "cookies_path": _cookie_store_path(cookies_path),
        "next_action": "continue" if logged_in else "prompt_qr_login",
    }


def start_qr_login(
    *,
    headers: dict[str, str] | None = None,
    max_retry: int = 10,
    retry_interval: float = 1.0,
    qr_image_path: str | Path | None = None,
) -> dict[str, object]:
    import qrcode

    request_headers = headers or {
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
        ),
    }
    last_error = "二维码生成失败"
    for _ in range(max_retry):
        response = requests.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            headers=request_headers,
            timeout=10,
        )
        payload = response.json()
        if payload.get("code") == 0:
            data = payload["data"]
            image_path_value: str | None = None
            if qr_image_path is not False:
                target = (
                    Path(qr_image_path)
                    if qr_image_path is not None
                    else Path(tempfile.gettempdir()) / "biliTickerBuy-login-qrcode.png"
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                qr = qrcode.QRCode(box_size=10, border=4)
                qr.add_data(data["url"])
                qr.make(fit=True)
                qr.make_image(fill_color="black", back_color="white").save(target)
                image_path_value = str(target)
            return {
                "ok": True,
                "login_url": data["url"],
                "qrcode_key": data["qrcode_key"],
                "qr_image_path": image_path_value,
                "next_action": "show_qr_and_confirm_scan",
            }
        last_error = payload.get("message", last_error)
        time.sleep(retry_interval)
    return {"ok": False, "error": last_error}


def poll_qr_login(
    qrcode_key: str,
    *,
    cookies_path: str | Path | None = None,
    timeout_seconds: float = 60.0,
    poll_interval: float = 0.5,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    from util.CookieManager import parse_cookie_list

    if not qrcode_key:
        raise ValueError("qrcode_key is required")

    request_headers = headers or {"User-Agent": "Mozilla/5.0"}
    deadline = time.time() + timeout_seconds
    last_message = "等待扫码"

    while time.time() < deadline:
        response = requests.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": qrcode_key},
            headers=request_headers,
            timeout=10,
        )
        payload = response.json()
        if payload.get("code") != 0:
            last_message = payload.get("message", "轮询登录失败")
            time.sleep(poll_interval)
            continue

        data = payload.get("data", {})
        state_code = data.get("code")
        last_message = data.get("message", last_message)

        if state_code == 0:
            cookies = parse_cookie_list(response.headers.get("set-cookie", ""))
            cookie_path_value = _cookie_store_path(cookies_path)
            request = _make_request(cookies=cookies, cookies_path=cookie_path_value)
            username = request.get_request_name()
            return {
                "ok": True,
                "status": "confirmed",
                "message": "登录成功",
                "cookies": cookies,
                "cookies_path": cookie_path_value,
                "username": username,
            }

        if state_code in (86101, 86090):
            time.sleep(poll_interval)
            continue

        return {
            "ok": False,
            "status": "failed",
            "message": last_message,
            "code": state_code,
        }

    return {"ok": False, "status": "timeout", "message": last_message or "登录超时"}


def login_with_cookies(
    cookies: list[dict[str, object]] | dict[str, object],
    *,
    cookies_path: str | Path | None = None,
) -> dict[str, object]:
    cookie_list = _resolve_cookie_list(cookies, cookies_path=cookies_path)
    username = _fetch_username_silently(cookie_list)
    return {
        "ok": True,
        "logged_in": username != "Not login",
        "username": username,
        "cookies": cookie_list,
        "cookies_path": _cookie_store_path(cookies_path),
    }
