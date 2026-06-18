from __future__ import annotations

import copy
import os
from dataclasses import MISSING, field, fields
from typing import Any, Callable, ClassVar


DEFAULT_CREATE_RETRY_LIMIT = 3
DEFAULT_CREATE_REQUEST_BATCH_SIZE = 1
DEFAULT_OUTER_LOOP_INTERVAL = 1000


def str_to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def normalize_log_level(value: Any) -> str:
    return str(value or "standard").lower()


def config_field(
    default: Any = MISSING,
    *,
    default_factory: Callable[[], Any] | Any = MISSING,
    env: str | None = None,
    runtime: str | None = None,
    db: str | None = None,
    cli: str | None = None,
    cast: Callable[[Any], Any] | None = None,
    env_default: Any = MISSING,
    runtime_default: Any = MISSING,
    db_default: Any = MISSING,
    env_transform: Callable[[Any], Any] | None = None,
    runtime_transform: Callable[[Any], Any] | None = None,
    db_transform: Callable[[Any], Any] | None = None,
    cli_false: str | None = None,
    cli_true: str | None = None,
    omit_cli_if_empty: bool = True,
):
    metadata = {
        "env": env,
        "runtime": runtime,
        "db": db,
        "cli": cli,
        "cast": cast,
        "env_default": env_default,
        "runtime_default": runtime_default,
        "db_default": db_default,
        "env_transform": env_transform,
        "runtime_transform": runtime_transform,
        "db_transform": db_transform,
        "cli_false": cli_false,
        "cli_true": cli_true,
        "omit_cli_if_empty": omit_cli_if_empty,
    }

    if default is not MISSING and default_factory is not MISSING:
        raise ValueError("不能同时传 default 和 default_factory")

    if default_factory is not MISSING:
        return field(default_factory=default_factory, metadata=metadata)

    if default is not MISSING:
        return field(default=default, metadata=metadata)

    return field(metadata=metadata)


def nested_config_field(default_factory: Callable[[], Any]):
    return field(
        default_factory=default_factory,
        metadata={
            "nested_config": True,
        },
    )


class BasicConfig:
    """
    通用配置基类。

    支持：
    1. from_env()
    2. from_mapping(...)
    3. from_config_getter(...)
    4. with_overrides(...)
    5. to_cli_args()
    """

    _skip_cli_fields: ClassVar[set[str]] = set()

    @classmethod
    def _field_default(cls, f) -> Any:
        if f.default is not MISSING:
            return copy.deepcopy(f.default)

        if f.default_factory is not MISSING:  # type: ignore[attr-defined]
            return f.default_factory()  # type: ignore[misc]

        return None

    @classmethod
    def _source_default(cls, f, source_name: str) -> Any:
        key = f"{source_name}_default"
        value = f.metadata.get(key, MISSING)

        if value is not MISSING:
            return copy.deepcopy(value)

        return cls._field_default(f)

    @staticmethod
    def _safe_apply(value: Any, func: Callable[[Any], Any] | None, default: Any) -> Any:
        if func is None:
            return value

        try:
            return func(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _normalize_value(cls, f, value: Any, *, source_name: str) -> Any:
        default = cls._source_default(f, source_name)

        if value is None:
            value = default

        cast = f.metadata.get("cast")
        value = cls._safe_apply(value, cast, default)

        transform = f.metadata.get(f"{source_name}_transform")
        value = cls._safe_apply(value, transform, default)

        return value

    @classmethod
    def _is_nested_config_field(cls, f) -> bool:
        return bool(f.metadata.get("nested_config"))

    @classmethod
    def from_mapping(
        cls,
        source: dict[str, Any],
        *,
        source_name: str,
    ):
        kwargs: dict[str, Any] = {}

        for f in fields(cls):
            if not f.init:
                continue

            if cls._is_nested_config_field(f):
                nested_cls = f.default_factory  # type: ignore[attr-defined]
                kwargs[f.name] = nested_cls.from_mapping(
                    source,
                    source_name=source_name,
                )
                continue

            source_key = f.metadata.get(source_name)
            if not source_key:
                continue

            default = cls._source_default(f, source_name)
            raw = source.get(source_key, default)

            kwargs[f.name] = cls._normalize_value(
                f,
                raw,
                source_name=source_name,
            )

        return cls(**kwargs)

    @classmethod
    def from_env(cls):
        kwargs: dict[str, Any] = {}

        for f in fields(cls):
            if not f.init:
                continue

            if cls._is_nested_config_field(f):
                nested_cls = f.default_factory  # type: ignore[attr-defined]
                kwargs[f.name] = nested_cls.from_env()
                continue

            env_key = f.metadata.get("env")
            if not env_key:
                continue

            default = cls._source_default(f, "env")
            raw = os.environ.get(env_key, default)

            kwargs[f.name] = cls._normalize_value(
                f,
                raw,
                source_name="env",
            )

        return cls(**kwargs)

    @classmethod
    def from_config_getter(
        cls,
        getter: Callable[[str], Any],
    ):
        kwargs: dict[str, Any] = {}

        for f in fields(cls):
            if not f.init:
                continue

            if cls._is_nested_config_field(f):
                nested_cls = f.default_factory  # type: ignore[attr-defined]
                kwargs[f.name] = nested_cls.from_config_getter(getter)
                continue

            db_key = f.metadata.get("db")
            if not db_key:
                continue

            default = cls._source_default(f, "db")
            raw = getter(db_key)

            if raw is None:
                raw = default

            kwargs[f.name] = cls._normalize_value(
                f,
                raw,
                source_name="db",
            )

        return cls(**kwargs)

    def with_overrides(self, **changes):
        payload = {
            f.name: copy.deepcopy(getattr(self, f.name)) for f in fields(self) if f.init
        }
        payload.update(changes)
        return type(self)(**payload)

    def to_cli_args(self) -> list[str]:
        args: list[str] = []

        def append_value(flag: str, value: Any, *, omit_if_empty: bool = True) -> None:
            if omit_if_empty and value in (None, ""):
                return
            args.extend([flag, str(value)])

        for f in fields(self):
            if not f.init:
                continue

            if f.name in self._skip_cli_fields:
                continue

            value = getattr(self, f.name)

            if self._is_nested_config_field(f):
                if isinstance(value, BasicConfig):
                    args.extend(value.to_cli_args())
                continue

            cli_true = f.metadata.get("cli_true")
            cli_false = f.metadata.get("cli_false")
            cli = f.metadata.get("cli")
            omit_cli_if_empty = bool(f.metadata.get("omit_cli_if_empty", True))

            if isinstance(value, bool):
                if value and cli_true:
                    args.append(cli_true)
                elif not value and cli_false:
                    args.append(cli_false)
                elif cli:
                    append_value(cli, value, omit_if_empty=omit_cli_if_empty)
                continue

            if cli:
                append_value(cli, value, omit_if_empty=omit_cli_if_empty)

        return args
