import json
import os
import shutil
from threading import RLock
from typing import Any, Optional

from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage, JSONStorage


def _ensure_valid_tinydb_file(path: str) -> None:
    """检查 TinyDB JSON 文件是否有效，无效则备份并重建。

    旧版本可能产生非 TinyDB 格式的 config.json（如平铺键值对、空对象、
    列表或损坏的 JSON）。此函数会检测并自动恢复，避免启动时闪退。
    """
    if not os.path.isfile(path):
        return  # 文件不存在，TinyDB 会自己创建

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError):
        # 损坏的 JSON → 备份并重建
        backup = path + ".bak"
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
        # 写一个空的 TinyDB 数据库
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_default": {}}, f)
        return

    # 不是 dict（例如是 list 或 bare string）→ 备份并重建
    if not isinstance(data, dict):
        backup = path + ".bak"
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_default": {}}, f)
        return

    # 已有 _default 表且内容有效 → 直接通过
    if "_default" in data and isinstance(data["_default"], dict):
        # 验证文档 ID 都是有效的整数，防止损坏的 ID（如 "bad"）导致 TinyDB 后续崩溃
        if all(
            isinstance(doc_id, str) and doc_id.isdigit() for doc_id in data["_default"]
        ):
            return

    # 平铺的旧版配置（flat dict，没有 _default 表）→ 迁移
    if not data:
        # 空 dict → 转为空的 TinyDB 格式
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_default": {}}, f)
        return

    # 尝试把平铺键值对转换为 TinyDB 文档
    docs = {}
    doc_id = 1
    for key, value in data.items():
        if isinstance(key, str):
            docs[str(doc_id)] = {"key": key, "value": value}
            doc_id += 1

    backup = path + ".bak"
    try:
        shutil.copy2(path, backup)
    except OSError:
        pass

    with open(path, "w", encoding="utf-8") as f:
        json.dump({"_default": docs}, f, ensure_ascii=False, indent=2)


class KVDatabase:
    # 同一个进程内，所有 KVDatabase 实例共享一把锁
    # 防止 Gradio / anyio 多线程同时写 TinyDB
    _lock = RLock()

    def __init__(self, db_path: Optional[str]):
        if db_path is None:
            self.db = TinyDB(storage=MemoryStorage)
        else:
            # 在初始化 TinyDB 之前先验证/修复文件格式
            _ensure_valid_tinydb_file(db_path)
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
