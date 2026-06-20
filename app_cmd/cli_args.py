from __future__ import annotations

import os
from dataclasses import dataclass

from app_cmd.config.BuyConfig import BuyConfig


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(f"BTB_{key}")
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_optional_int(*keys: str) -> int | None:
    for key in keys:
        raw = os.environ.get(key)
        if raw not in (None, ""):
            return int(raw)
    return None


def _env_optional_str(*keys: str) -> str | None:
    for key in keys:
        raw = os.environ.get(key)
        if raw not in (None, ""):
            return raw
    return None


@dataclass(slots=True)
class TickerCliArgs:
    """Web UI launch options."""

    share: bool = _env_bool("SHARE", False)
    """Expose the Gradio app publicly."""

    server_name: str = os.environ.get("BTB_SERVER_NAME", "127.0.0.1")
    """Bind address for the UI server."""

    port: int | None = _env_optional_int("BTB_PORT", "GRADIO_SERVER_PORT")
    """Port for the UI server. Defaults to Gradio or environment configuration."""

    root_path: str | None = _env_optional_str("BTB_ROOT_PATH", "GRADIO_ROOT_PATH")
    """External URL or root path used when the UI is accessed through a remote IP, domain, or reverse proxy."""


BuyCliArgs = BuyConfig
