from dataclasses import dataclass
from typing import Optional

import requests

from util.Storage.KVDatabase import KVDatabase


@dataclass
class Account:
    """B站账号信息"""

    uid: str
    name: str
    face: str
    cookies: list[dict]
    level: int = 0
    is_vip: bool = False
    coins: float = 0.0


def parse_cookie_list(cookie_str: str) -> list:
    cookies = []
    parts = cookie_str.split(",")

    merged = []
    current = ""
    for part in parts:
        if "=" in part.split(";", 1)[0]:
            if current:
                merged.append(current.strip())
            current = part
        else:
            current += "," + part
    if current:
        merged.append(current.strip())

    for item in merged:
        if ";" in item:
            key_value = item.split(";", 1)[0]
        else:
            key_value = item
        if "=" in key_value:
            key, value = key_value.split("=", 1)
            cookies.append({"name": key.strip(), "value": value.strip()})
    return cookies


class CookieManager:
    """
    管理 cookies.json，包含多账号和配置
    cookies.json 结构示例：
    {
    "_default": {
        "1": {"key": "cookie",   "value": [{"name": "SESSDATA", "value": "xxx"}, ...]}, //当前账号cookie
        "2": {"key": "phone",    "value": "13812345678"},            //手机号
        "3": {"key": "accounts", "value": [                         //账号列表
        {
            "uid": "123456",
            "name": "用户A",
            "face": "https://...",
            "cookies": [{"name": "SESSDATA", "value": "xxx"}, ...],
            "level": 6,
            "is_vip": true,
            "coins": 12.5
        },
        {
            "uid": "789012",
            "name": "用户B",
            ...
        }
        ]}
    }
    }
    """

    # 数据库中的键
    _COOKIE_KEY = "cookie"  # 当前账号的 cookie
    _PHONE_KEY = "phone"  # 手机号
    _ACCOUNTS_KEY = "accounts"  # 所有账号列表 List[Account]

    def __init__(self, config_file_path=None, cookies=None):
        self.db = KVDatabase(config_file_path)
        if cookies is not None:
            self.db.insert(self._COOKIE_KEY, cookies)

    # ---------- 当前账号 cookie 操作 ----------

    def get_cookies(self, force=False):
        if force:
            return self.db.get(self._COOKIE_KEY)
        if not self.db.contains(self._COOKIE_KEY):
            raise RuntimeError("当前未登录，请登录")
        else:
            return self.db.get(self._COOKIE_KEY)

    def have_cookies(self):
        return self.db.contains(self._COOKIE_KEY)

    def get_cookies_str(self):
        cookies = self.get_cookies()
        cookies_str = ""
        assert cookies
        for cookie in cookies:
            cookies_str += cookie["name"] + "=" + cookie["value"] + "; "
        return cookies_str

    def get_cookies_value(self, name):
        cookies = self.get_cookies()
        assert cookies
        for cookie in cookies:
            if cookie["name"] == name:
                return cookie["value"]
        return None

    def get_config_value(self, name, default=None):
        if self.db.contains(name):
            return self.db.get(name)
        else:
            return default

    def set_config_value(self, name, value):
        self.db.insert(name, value)

    # ---------- 多账号管理 ----------

    def get_accounts(self) -> list[Account]:
        """返回所有已保存的账号"""
        raw = self.db.get(self._ACCOUNTS_KEY)
        if not raw or not isinstance(raw, list):
            return []
        return [Account(**a) for a in raw if isinstance(a, dict)]

    def add_account(self, cookies: list[dict]) -> Account:
        """
        扫码或导入后调用。调 B站 API 获取用户信息，按 uid 去重后保存。
        """
        user_info = self._fetch_user_info(cookies)
        account = Account(
            uid=user_info["uid"],
            name=user_info["name"],
            face=user_info["face"],
            cookies=cookies,
            level=user_info["level"],
            is_vip=user_info["is_vip"],
            coins=user_info["coins"],
        )

        accounts = [a for a in self.get_accounts() if a.uid != account.uid]
        accounts.append(account)
        self._save_accounts(accounts)

        return account

    def remove_account(self, uid: str) -> None:
        accounts = [a for a in self.get_accounts() if a.uid != uid]
        self._save_accounts(accounts)

    def find_by_uid(self, uid: str) -> Optional[Account]:
        for a in self.get_accounts():
            if a.uid == uid:
                return a
        return None

    def _save_accounts(self, accounts: list[Account]) -> None:
        self.db.insert(self._ACCOUNTS_KEY, [a.__dict__ for a in accounts])

    @staticmethod
    def _fetch_user_info(cookies: list[dict]) -> dict:
        """用 cookies 调 B站 API 获取用户信息"""
        cookies_str = ""
        for cookie in cookies:
            cookies_str += f"{cookie['name']}={cookie['value']}; "

        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "referer": "https://show.bilibili.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "cookie": cookies_str.strip(),
        }

        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {}) or {}

        return {
            "uid": str(data.get("mid", "")),
            "name": str(data.get("uname", "") or ""),
            "face": str(data.get("face", "") or ""),
            "level": data.get("level_info", {}).get("current_level", 0) or 0,
            "is_vip": data.get("vipStatus", 0) == 1,
            "coins": float(data.get("money", 0.0) or 0.0),
        }
