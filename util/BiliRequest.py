import secrets
import time

import loguru
import requests
from requests import Response
from util.BrowerState import (
    BrowserFingerprintState,
    build_headers_from_browser_state,
    finalize_device_id,
    generate_browser_fingerprint_state,
)
from util.CookieManager import CookieManager
from util.ProxyManager import ProxyManager


class BiliRequest:
    def __init__(
        self,
        headers=None,
        cookies=None,
        cookies_config_path=None,
        proxy: str = "none",
        browser_state: BrowserFingerprintState | None = None,
    ):
        self.browser_state = browser_state or generate_browser_fingerprint_state()
        self.deviceId = finalize_device_id(secrets.token_hex(16))
        self.session = requests.Session()
        self.proxy_manager = ProxyManager(proxy)
        self.cookieManager = CookieManager(cookies_config_path, cookies)
        self.headers = build_headers_from_browser_state(
            self.browser_state,
            base_headers=headers,
            referer="https://show.bilibili.com/",
            content_type="application/x-www-form-urlencoded",
        )
        self.request_count = 0  # 记录请求次数
        self.proxy_manager.apply_to_session(self.session)
        self.createTime = int(time.time() * 1000)

    def _rotate_proxy(self, reason: str) -> bool:
        if not self.proxy_manager.rotate():
            return False
        self.proxy_manager.apply_to_session(self.session)
        return True

    def get_user_agent(self) -> str:
        return self.headers.get("user-agent", "")

    def snapshot_proxy_state(self) -> int:
        return self.proxy_manager.snapshot()

    def restore_proxy_state(self, state: int) -> None:
        self.proxy_manager.restore(state)
        self.proxy_manager.apply_to_session(self.session)

    def clear_request_count(self):
        self.request_count = 0

    def get(self, url, data=None, isJson=False):
        return self._request("get", url, data=data, isJson=isJson)

    def switch_proxy(self):
        return self._rotate_proxy("手动切换代理")

    def post(self, url, data=None, isJson=False):
        return self._request("post", url, data=data, isJson=isJson)

    def current_proxy_display(self) -> str:
        return self.proxy_manager.current_proxy_display

    def current_proxy_status(self) -> str:
        return self.proxy_manager.current_proxy_status()

    def proxy_pool_status(self) -> str:
        return self.proxy_manager.proxy_pool_status()

    def has_available_proxy(self) -> bool:
        return self.proxy_manager.has_available_proxy()

    def is_current_proxy_available(self) -> bool:
        return self.proxy_manager.is_current_proxy_available()

    def ensure_active_proxy(self) -> bool:
        if not self.proxy_manager.ensure_current_available():
            return False
        self.proxy_manager.apply_to_session(self.session)
        return True

    def mark_current_proxy_failure(self, reason: str) -> bool:
        return self.proxy_manager.mark_current_failure(reason)

    def mark_current_proxy_success(self) -> None:
        self.proxy_manager.mark_current_success()

    def describe_non_json_response(
        self, response: Response, body_limit: int = 300
    ) -> str:
        content_type = response.headers.get("Content-Type", "未知")
        body = response.text or ""
        body = body.replace("\r", "\\r").replace("\n", "\\n")
        if len(body) > body_limit:
            body = body[:body_limit] + "..."
        if not body:
            body = "<empty>"
        return (
            f"status={response.status_code}, "
            f"content_type={content_type}, "
            f"url={response.url}, "
            f"body_preview={body}"
        )

    def _request(self, method: str, url, data=None, isJson=False):
        self.headers["cookie"] = self.cookieManager.get_cookies_str()
        if isJson:
            self.headers["Content-Type"] = "application/json"
            response = self.session.request(
                method, url, json=data, headers=self.headers, timeout=10
            )
        else:
            self.headers["Content-Type"] = "application/x-www-form-urlencoded"
            request_kwargs = (
                {"params": data} if method.lower() == "get" else {"data": data}
            )
            response = self.session.request(
                method,
                url,
                headers=self.headers,
                timeout=10,
                **request_kwargs,
            )

        if response.status_code == 412:
            self.request_count += 1
            return response

        response.raise_for_status()
        self.clear_request_count()
        self.mark_current_proxy_success()
        if response.json().get("msg", "") == "请先登录":
            raise RuntimeError("当前未登录，请重新登陆")
        return response

    def get_request_name(self):
        try:
            if not self.cookieManager.have_cookies():
                loguru.logger.warning("获取用户名失败，请重新登录")
                return "未登录"
            result = self.get("https://api.bilibili.com/x/web-interface/nav").json()
            return result["data"]["uname"]
        except Exception:
            return "未登录"
