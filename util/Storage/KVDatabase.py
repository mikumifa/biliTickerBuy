from threading import RLock
from typing import Any, Optional

from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage, JSONStorage


class KVDatabase:
    # 同一个进程内，所有 KVDatabase 实例共享一把锁
    # 防止 Gradio / anyio 多线程同时写 TinyDB
    _lock = RLock()

    def __init__(self, db_path: Optional[str]):
        if db_path is None:
            self.db = TinyDB(storage=MemoryStorage)
        else:
            self.db = TinyDB(db_path, storage=JSONStorage)

        self.KeyValue = Query()

    def insert(self, key: str, value: Any) -> None:
        """
        插入或更新键值对。

        如果 key 已存在，则更新 value；
        如果 key 不存在，则插入新的 key-value。
        """
        with self._lock:
            self.db.upsert(
                {"key": key, "value": value},
                self.KeyValue.key == key,
            )

    def get(self, key: str) -> Any:
        """
        获取 key 对应的 value。

        如果 key 不存在，返回 None。
        """
        try:
            with self._lock:
                result = self.db.get(self.KeyValue.key == key)
        except Exception:
            return None

        return result["value"] if result else None

    def get_as_int(self, key: str, default: int) -> int:
        raw = self.get(key)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return value

    def get_as_bool(self, key: str, default: bool) -> bool:
        value = self.get(key)
        if value is None:
            return default
        return bool(value)

    def update(self, key: str, value: Any) -> None:
        """
        更新已存在的 key。

        如果 key 不存在，抛出 KeyError。
        """
        with self._lock:
            if self.db.contains(self.KeyValue.key == key):
                self.db.update(
                    {"value": value},
                    self.KeyValue.key == key,
                )
            else:
                raise KeyError(f"Key '{key}' not found in database.")

    def delete(self, key: str) -> None:
        """
        删除 key。
        """
        with self._lock:
            self.db.remove(self.KeyValue.key == key)

    def contains(self, key: str) -> bool:
        """
        判断 key 是否存在。
        """
        with self._lock:
            return self.db.contains(self.KeyValue.key == key)

    def close(self) -> None:
        """
        关闭数据库。

        如果程序退出前想主动释放文件句柄，可以调用。
        """
        with self._lock:
            self.db.close()
