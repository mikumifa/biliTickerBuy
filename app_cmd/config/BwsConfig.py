from dataclasses import dataclass

from app_cmd.config.ConfigBasic import BasicConfig, config_field, str_to_bool


@dataclass(slots=True)
class BwsConfig(BasicConfig):
    """BW park reservation runtime configuration."""

    reserve_id: int = config_field(
        0,
        env="BTB_BWS_RESERVE_ID",
        runtime="reserve_id",
        cli="--reserve-id",
        cast=int,
    )
    """BW park reservation activity id."""

    reserve_dates: str = config_field(
        "",
        env="BTB_BWS_RESERVE_DATES",
        runtime="reserve_dates",
        cli="--reserve-dates",
    )
    """Comma-separated dates, for example 20260710,20260711,20260712."""

    reserve_date: str = config_field(
        "",
        env="BTB_BWS_RESERVE_DATE",
        runtime="reserve_date",
        cli="--reserve-date",
    )
    """Target date used to pick the activated ticket number."""

    reserve_type: int = config_field(
        -1,
        env="BTB_BWS_RESERVE_TYPE",
        runtime="reserve_type",
        cli="--reserve-type",
        cast=int,
    )
    """Reservation type: -1 for all, 0 for activities, 1 for goods."""

    year: str = config_field(
        "",
        env="BTB_BWS_YEAR",
        runtime="year",
        cli="--year",
    )
    """Optional BW API year value, for example 202601."""

    time_start: str = config_field(
        "",
        env="BTB_BWS_TIME_START",
        runtime="time_start",
        cli="--time-start",
    )
    """Optional scheduled start time overriding activity reserve_begin_time."""

    start_delay_ms: int = config_field(
        0,
        env="BTB_BWS_START_DELAY_MS",
        runtime="start_delay_ms",
        cli="--start-delay-ms",
        cast=int,
    )
    """Delay added to the scheduled start time; negative values start early."""

    interval: int = config_field(
        300,
        env="BTB_BWS_INTERVAL",
        runtime="interval",
        cli="--interval",
        cast=int,
    )
    """Retry interval in milliseconds."""

    retry_limit: int = config_field(
        0,
        env="BTB_BWS_RETRY_LIMIT",
        runtime="retry_limit",
        cli="--retry-limit",
        cast=int,
    )
    """Maximum submit attempts; 0 means retry until terminal result."""

    cookies_path: str = config_field(
        "",
        env="BTB_BWS_COOKIES_PATH",
        runtime="cookies_path",
        cli="--cookies-path",
    )
    """Cookie store path. Defaults to the app's existing login cookie store."""

    https_proxys: str = config_field(
        "none",
        env="BTB_HTTPS_PROXYS",
        runtime="https_proxys",
        cli="--https-proxys",
    )
    """Proxy string or comma-separated proxy pool."""

    show_detail: bool = config_field(
        True,
        env="BTB_BWS_SHOW_DETAIL",
        runtime="show_detail",
        cast=str_to_bool,
        cli_false="--no-show-detail",
    )
    """Print selected activity and ticket details before submitting."""
