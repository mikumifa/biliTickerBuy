from __future__ import annotations

import os
from dataclasses import dataclass

from config.BuyConfig import BuyConfig


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


@dataclass(slots=True)
class TickerCliArgs:
    """Web UI launch options."""

    share: bool = _env_bool("SHARE", False)
    """Expose the Gradio app publicly."""

    server_name: str = os.environ.get("BTB_SERVER_NAME", "127.0.0.1")
    """Bind address for the UI server."""

    port: int | None = _env_optional_int("BTB_PORT", "GRADIO_SERVER_PORT")
    """Port for the UI server. Defaults to Gradio or environment configuration."""


BuyCliArgs = BuyConfig
