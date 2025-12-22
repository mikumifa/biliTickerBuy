import argparse
import os


def get_env_default(key: str, default, cast_func):
    return cast_func(os.environ.get(f"BTB_{key}", default))


def str_to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def main():
    gradio_parent = argparse.ArgumentParser(add_help=False)
    gradio_parent.add_argument(
        "--share",
        action="store_true",
        default=get_env_default("SHARE", False, str_to_bool),
        help="Share Gradio app publicly (tunnel). Defaults to False.",
    )
    gradio_parent.add_argument(
        "--server_name",
        type=str,
        default=os.environ.get("BTB_SERVER_NAME", "127.0.0.1"),
        help='Server name for Gradio. Defaults to env "BTB_SERVER_NAME" or 127.0.0.1.',
    )
    gradio_parent.add_argument(
        "--port",
        type=int,
        default=os.environ.get("BTB_PORT", os.environ.get("GRADIO_SERVER_PORT", None)),
        help='Server port for Gradio. Defaults to env "BTB_PORT"/"GRADIO_SERVER_PORT" or 7860.',
    )

    parser = argparse.ArgumentParser(
        description=(
            "BiliTickerBuy\n\n"
            "Use `btb buy` to buy tickets directly in the command line."
            "Run `btb` without arguments to open the UI."
            "Run `btb buy -h` for `btb buy` detailed options."
        ),
        epilog=(
            "Examples:\n"
            "  btb buy tickets.json\n"
            "  btb buy tickets.json --interval 500\n\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        parents=[gradio_parent],
    )
    subparsers = parser.add_subparsers(
        dest="command",
        title="Available Commands",
        metavar="{buy}",
        description="Use one of the following commands",
    )
    buy_parser = subparsers.add_parser(
        "buy",
        help="Buy tickets directly in the command line",
        parents=[gradio_parent],
    )
    # ===== Buy Core =====
    buy_core = buy_parser.add_argument_group("Buy Core Options")
    buy_core.add_argument(
        "tickets_info",
        type=str,
        help="Ticket information in JSON format or a path to a JSON config file.",
    )
    buy_core.add_argument(
        "--interval",
        type=int,
        default=1000,
        help="Interval time (ms). Defaults to 1000 if omitted.",
    )
    buy_core.add_argument(
        "--endpoint_url",
        type=str,
        default=os.environ.get("BTB_ENDPOINT_URL", ""),
        help="Endpoint URL.",
    )
    buy_core.add_argument(
        "--time_start",
        type=str,
        default=os.environ.get("BTB_TIME_START", ""),
        help="Start time (optional).",
    )
    buy_core.add_argument(
        "--https_proxys",
        type=str,
        default=os.environ.get("BTB_HTTPS_PROXYS", "none"),
        help="HTTPS proxy, e.g. http://127.0.0.1:8080",
    )

    # ===== Notifications =====
    notify = buy_parser.add_argument_group("Notification Options")

    notify.add_argument(
        "--audio_path",
        type=str,
        default=os.environ.get("BTB_AUDIO_PATH", ""),
        help="Path to audio file (optional).",
    )
    notify.add_argument(
        "--pushplusToken",
        type=str,
        default=os.environ.get("BTB_PUSHPLUSTOKEN", ""),
        help="PushPlus token (optional).",
    )
    notify.add_argument(
        "--serverchanKey",
        type=str,
        default=os.environ.get("BTB_SERVERCHANKEY", ""),
        help="ServerChan key (optional).",
    )
    notify.add_argument(
        "--serverchan3ApiUrl",
        type=str,
        default=os.environ.get("BTB_SERVERCHAN3APIURL", ""),
        help="ServerChan3 API URL (optional).",
    )
    notify.add_argument(
        "--barkToken",
        type=str,
        default=os.environ.get("BTB_BARKTOKEN", ""),
        help="Bark token (optional).",
    )
    notify.add_argument(
        "--ntfy_url",
        type=str,
        default=os.environ.get("BTB_NTFY_URL", ""),
        help="Ntfy server URL, e.g. https://ntfy.sh/topic",
    )
    notify.add_argument(
        "--ntfy_username",
        type=str,
        default=os.environ.get("BTB_NTFY_USERNAME", ""),
        help="Ntfy username (optional).",
    )
    notify.add_argument(
        "--ntfy_password",
        type=str,
        default=os.environ.get("BTB_NTFY_PASSWORD", ""),
        help="Ntfy password (optional).",
    )

    # ===== Runtime / UI =====
    runtime = buy_parser.add_argument_group("Runtime & UI Options")
    runtime.add_argument(
        "--web",
        action="store_true",
        help="Run with web UI instead of terminal output (useful on macOS).",
    )
    runtime.add_argument(
        "--hide_random_message",
        action="store_true",
        help="Hide random message when fail.",
    )

    args = parser.parse_args()
    if args.command == "buy":
        from app_cmd.buy import buy_cmd

        buy_cmd(args=args)
    else:
        from app_cmd.ticker import ticker_cmd

        ticker_cmd(args=args)


if __name__ == "__main__":
    main()
