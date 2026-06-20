from dataclasses import dataclass
import os
from typing import Any, ClassVar

from app_cmd.config.ConfigBasic import (
    BasicConfig,
    DEFAULT_CREATE_REQUEST_BATCH_SIZE,
    DEFAULT_CREATE_RETRY_LIMIT,
    config_field,
    nested_config_field,
    normalize_log_level,
    str_to_bool,
)
from app_cmd.config.NotifierConfig import NotifierConfig


@dataclass(slots=True)
class BuyConfig(BasicConfig):
    """Ticket buying runtime configuration."""

    _skip_cli_fields: ClassVar[set[str]] = {"tickets_info", "config_file"}

    tickets_info: str = ""
    """Ticket JSON content passed to the buyer."""

    config_file: str = config_field(
        "",
        cli="--config-file",
    )
    """Path to a ticket configuration JSON file."""

    time_start: str = config_field(
        "",
        env="BTB_TIME_START",
        runtime="time_start",
        cli="--time-start",
    )
    """Scheduled start time, for example 2026-06-18T20:00:00."""

    interval: int | None = config_field(
        1000,
        env="BTB_INTERVAL",
        runtime="interval",
        db="requestInterval",
        cli="--interval",
        cast=int,
    )
    """Default request interval in milliseconds."""

    notifier_config: NotifierConfig = nested_config_field(NotifierConfig)
    """Notification settings."""

    https_proxys: str = config_field(
        "none",
        env="BTB_HTTPS_PROXYS",
        runtime="https_proxys",
        db="https_proxy",
        cli="--https-proxys",
    )
    """Proxy string or comma-separated proxy pool."""

    # ConfigDB 里原字段是 hideRandomMessage，语义和 show_random_message 相反
    show_random_message: bool = config_field(
        True,
        runtime="show_random_message",
        db="hideRandomMessage",
        db_default=True,
        cast=str_to_bool,
        db_transform=lambda hide: not hide,
        cli_false="--no-show-random-message",
    )
    """Show random failure messages after a round fails."""

    show_qrcode: bool = config_field(
        True,
        runtime="show_qrcode",
        db="showQrcode",
        db_default=True,
        cast=str_to_bool,
        cli_false="--no-show-qrcode",
    )
    """Show the payment QR code after a successful order."""

    use_local_token: bool = config_field(
        False,
        env="BTB_USE_LOCAL_TOKEN",
        runtime="use_local_token",
        db="useLocalToken",
        cast=str_to_bool,
        cli_true="--use-local-token",
    )
    """Use locally generated token when the project flow allows it."""

    create_retry_limit: int = config_field(
        DEFAULT_CREATE_RETRY_LIMIT,
        env="BTB_CREATE_RETRY_LIMIT",
        runtime="create_retry_limit",
        db="createRetryLimit",
        cli="--create-retry-limit",
        cast=int,
    )
    """Maximum create-order attempts per round."""

    create_request_batch_size: int = config_field(
        DEFAULT_CREATE_REQUEST_BATCH_SIZE,
        env="BTB_CREATE_REQUEST_BATCH_SIZE",
        runtime="create_request_batch_size",
        db="createRequestBatchSize",
        cli="--create-request-batch-size",
        cast=int,
    )
    """Number of create-order requests sent in one batch."""

    proxy_max_consecutive_failures: int = config_field(
        10,
        env="BTB_PROXY_MAX_CONSECUTIVE_FAILURES",
        runtime="proxy_max_consecutive_failures",
        db="proxyMaxConsecutiveFailures",
        cli="--proxy-max-consecutive-failures",
        cast=int,
    )
    """Failures before one proxy is temporarily cooled down."""

    proxy_cooldown_seconds: int = config_field(
        60,
        env="BTB_PROXY_COOLDOWN_SECONDS",
        runtime="proxy_cooldown_seconds",
        db="proxyCooldownSeconds",
        cli="--proxy-cooldown-seconds",
        cast=int,
    )
    """Cooldown duration for a failed proxy, in seconds."""

    proxy_backoff_max_seconds: int = config_field(
        240,
        env="BTB_PROXY_BACKOFF_MAX_SECONDS",
        runtime="proxy_backoff_max_seconds",
        db="proxyBackoffMaxSeconds",
        cli="--proxy-backoff-max-seconds",
        cast=int,
    )
    """Maximum sleep time when the whole proxy pool is unavailable."""

    # 你原来的 from_config_db 里 ConfigDB 缺省时是 True，这里保留这个行为
    auto_open_payment_url: bool = config_field(
        False,
        runtime="auto_open_payment_url",
        db="autoOpenPaymentUrl",
        db_default=True,
        cast=str_to_bool,
        cli_true="--auto-open-payment-url",
    )
    """Open the payment page automatically after success."""

    log_level: str = config_field(
        "standard",
        env="BTB_LOG_LEVEL",
        runtime="log_level",
        db="logLevel",
        cli="--log-level",
        cast=normalize_log_level,
    )
    """Console logging preset: simple, standard, or debug."""

    log_retention_days: int = config_field(
        7,
        env="BTB_LOG_RETENTION_DAYS",
        runtime="log_retention_days",
        db="logRetentionDays",
        cli="--log-retention-days",
        cast=int,
    )
    """Retention period for generated log files, in days."""

    @classmethod
    def from_runtime_options(
        cls,
        tickets_info: str,
        runtime_options,
        *,
        show_qrcode: bool | None = None,
    ) -> "BuyConfig":
        data = (
            runtime_options.to_dict()
            if hasattr(runtime_options, "to_dict")
            else dict(runtime_options)
        )

        config = cls.from_mapping(data, source_name="runtime").with_overrides(
            tickets_info=tickets_info,
        )

        if show_qrcode is not None:
            config = config.with_overrides(show_qrcode=show_qrcode)

        return config

    @classmethod
    def from_config_db(
        cls,
        *,
        tickets_info: str = "",
        time_start: str = "",
        interval: int | None = None,
        https_proxys: str | None = None,
        show_qrcode: bool | None = None,
    ) -> "BuyConfig":
        from util import ConfigDB

        config = cls.from_config_getter(ConfigDB.get)

        overrides: dict[str, Any] = {
            "tickets_info": tickets_info,
            "time_start": time_start,
        }

        if interval is not None:
            overrides["interval"] = interval

        if https_proxys is not None:
            overrides["https_proxys"] = https_proxys

        if show_qrcode is not None:
            overrides["show_qrcode"] = show_qrcode

        return config.with_overrides(**overrides)

    def apply_log_env(self) -> None:
        normalized_log_level = normalize_log_level(self.log_level)

        if normalized_log_level == "simple":
            os.environ["BTB_LOG_LEVEL"] = "INFO"
            os.environ["BTB_CONSOLE_LOG_LEVEL"] = "INFO"
        elif normalized_log_level == "debug":
            os.environ["BTB_LOG_LEVEL"] = "DEBUG"
            os.environ["BTB_CONSOLE_LOG_LEVEL"] = "DEBUG"
        else:
            os.environ["BTB_LOG_LEVEL"] = "DEBUG"
            os.environ["BTB_CONSOLE_LOG_LEVEL"] = "INFO"

        os.environ["BTB_LOG_RETENTION_DAYS"] = str(max(1, int(self.log_retention_days)))
