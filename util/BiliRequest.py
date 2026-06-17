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

DEFAULT_TIMEOUT = (3.05, 8)


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
        self.use_h2 = False
        self._h2_client = None
        self.createTime = int(time.time() * 1000)

    def _rotate_proxy(self, reason: str) -> bool:
        if not self.proxy_manager.rotate():
            return False
        self.proxy_manager.apply_to_session(self.session)
        self._invalidate_h2_client()
        return True

    def _invalidate_h2_client(self):
        if self._h2_client is None:
            return
        try:
            self._h2_client.close()
        except Exception:
            pass
        self._h2_client = None

    def get_user_agent(self) -> str:
        return self.headers.get("user-agent", "")

    def snapshot_proxy_state(self) -> int:
        return self.proxy_manager.snapshot()

    def restore_proxy_state(self, state: int) -> None:
        self.proxy_manager.restore(state)
        self.proxy_manager.apply_to_session(self.session)
        self._invalidate_h2_client()

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

    def _build_h2_client(self):
        import httpx

        proxies = self.session.proxies or {}
        proxy = proxies.get("https") or proxies.get("http") or None
        verify = (
            self.session.verify
            if isinstance(self.session.verify, (bool, str))
            else True
        )
        return httpx.Client(
            http2=True,
            verify=verify,
            proxy=proxy,
            timeout=DEFAULT_TIMEOUT,
            headers={
                "accept": "*/*",
                "accept-encoding": "gzip, deflate, br, zstd",
                "connection": "keep-alive",
                "user-agent": self.headers.get("user-agent", ""),
            },
        )

    def _h2_send(self, method: str, url, data=None, isJson=False):
        if self._h2_client is None:
            self._h2_client = self._build_h2_client()
        client = self._h2_client
        client.headers["user-agent"] = self.headers.get("user-agent", "")
        for cookie in self.cookieManager.get_cookies(force=True) or []:
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                client.cookies.set(name, value, domain=".bilibili.com")
        if method.lower() == "post":
            return (
                client.post(url, json=data) if isJson else client.post(url, data=data)
            )
        return client.get(url, params=data)

    def _request(self, method: str, url, data=None, isJson=False):
        if self.use_h2:
            return self._h2_send(method, url, data=data, isJson=isJson)
        self.headers["cookie"] = self.cookieManager.get_cookies_str()
        if isJson:
            self.headers["Content-Type"] = "application/json"
            response = self.session.request(
                method, url, json=data, headers=self.headers, timeout=DEFAULT_TIMEOUT
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
                timeout=DEFAULT_TIMEOUT,
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
