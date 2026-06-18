import requests

from util.proxy.ProxyState import ProxyStateRegistry


class ProxyManager:
    def __init__(
        self,
        proxy_string: str = "none",
        *,
        failure_threshold: int = 2,
        cooldown_seconds: float = 180.0,
    ):
        self.proxy_list = self.parse_proxy_list(proxy_string)
        if not self.proxy_list:
            raise ValueError("at least have none proxy")
        self.state_registry = ProxyStateRegistry(
            self.proxy_list,
            mask_proxy=self.mask_proxy_value,
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
        )

    @property
    def now_proxy_idx(self) -> int:
        return self.state_registry.current_index

    @now_proxy_idx.setter
    def now_proxy_idx(self, index: int) -> None:
        self.state_registry.set_current_index(index)

    @staticmethod
    def normalize_proxy_value(proxy: str) -> str:
        proxy = (proxy or "").strip()
        if not proxy:
            return ""
        if proxy.lower() in {"none", "direct"}:
            return "none"
        return proxy

    @classmethod
    def parse_proxy_list(
        cls, proxy_string: str | None, include_direct_fallback: bool = False
    ) -> list[str]:
        proxy_list = []
        if proxy_string:
            proxy_list = [
                cls.normalize_proxy_value(item)
                for item in proxy_string.split(",")
                if item and item.strip()
            ]

        normalized: list[str] = []
        seen: set[str] = set()
        for item in proxy_list:
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(item)

        if include_direct_fallback and "none" not in seen:
            normalized.insert(0, "none")

        return normalized

    @staticmethod
    def mask_proxy_value(proxy: str) -> str:
        proxy = (proxy or "").strip()
        if not proxy:
            return ""
        if proxy.lower() in {"none", "direct"}:
            return "直连"
        if "://" not in proxy:
            return proxy

        scheme, remainder = proxy.split("://", 1)
        if "@" not in remainder:
            return proxy

        _, host_part = remainder.rsplit("@", 1)
        return f"{scheme}://***:***@{host_part}"

    @classmethod
    def mask_proxy_string(cls, proxy_string: str | None) -> str:
        proxies = cls.parse_proxy_list(proxy_string)
        masked = [cls.mask_proxy_value(proxy) for proxy in proxies]
        return ",".join(item for item in masked if item)

    @property
    def current_proxy(self) -> str:
        return self.proxy_list[self.now_proxy_idx]

    @property
    def current_proxy_display(self) -> str:
        return self.mask_proxy_value(self.current_proxy)

    def current_proxy_status(self) -> str:
        return self.state_registry.current_status_text()

    def proxy_pool_status(self) -> str:
        return self.state_registry.describe_all_states()

    def snapshot(self) -> int:
        return self.now_proxy_idx

    def restore(self, index: int) -> None:
        self.now_proxy_idx = index

    def apply_to_session(self, session: requests.Session) -> None:
        session.trust_env = False
        if self.current_proxy == "none":
            session.proxies = {}
            return
        session.proxies = {
            "http": self.current_proxy,
            "https": self.current_proxy,
        }

    def rotate(self) -> bool:
        return self.state_registry.switch_to_next_available()

    def ensure_current_available(self) -> bool:
        return self.state_registry.ensure_current_available()

    def has_available_proxy(self) -> bool:
        return self.state_registry.has_available_proxy()

    def is_current_proxy_available(self) -> bool:
        return self.state_registry.is_current_available()

    def mark_current_success(self) -> None:
        self.state_registry.record_current_success()

    def mark_current_failure(self, reason: str) -> bool:
        return self.state_registry.record_current_failure(reason)
