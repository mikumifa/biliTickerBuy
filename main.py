import argparse
import os


def get_env_default(key: str, default, cast_func):
    return cast_func(os.environ.get(f"BTB_{key}", default))


def main():
    parser = argparse.ArgumentParser(description="Ticket Purchase Tool or Gradio UI")
    subparsers = parser.add_subparsers(dest="command")
    buy_parser = subparsers.add_parser("buy", help="Start the ticket buying ui")
    buy_parser.add_argument(
        "tickets_info_str", type=str, help="Ticket information in string format."
    )
    buy_parser.add_argument("interval", type=int, help="Interval time.")
    buy_parser.add_argument("mode", type=int, help="Mode of operation.")
    buy_parser.add_argument(
        "total_attempts", type=int, help="Total number of attempts."
    )
    buy_parser.add_argument(
        "--endpoint_url",
        type=str,
        default=os.environ.get("BTB_ENDPOINT_URL", ""),
        help="endpoint_url.",
    )
    buy_parser.add_argument(
        "--time_start",
        type=str,
        default=os.environ.get("BTB_TIME_START", ""),
        help="Start time (optional)",
    )
    buy_parser.add_argument(
        "--audio_path",
        type=str,
        default=os.environ.get("BTB_AUDIO_PATH", ""),
        help="Path to audio file (optional).",
    )
    buy_parser.add_argument(
        "--pushplusToken",
        type=str,
        default=os.environ.get("BTB_PUSHPLUSTOKEN", ""),
        help="PushPlus token (optional).",
    )
    buy_parser.add_argument(
        "--serverchanKey",
        type=str,
        default=os.environ.get("BTB_SERVERCHANKEY", ""),
        help="ServerChan key (optional).",
    )
    buy_parser.add_argument(
        "--ntfy_url",
        type=str,
        default=os.environ.get("BTB_NTFY_URL", ""),
        help="Ntfy server URL (optional). e.g., https://ntfy.sh/topic",
    )
    buy_parser.add_argument(
        "--ntfy_username",
        type=str,
        default=os.environ.get("BTB_NTFY_USERNAME", ""),
        help="Ntfy username (optional). For authenticated ntfy servers.",
    )
    buy_parser.add_argument(
        "--ntfy_password",
        type=str,
        default=os.environ.get("BTB_NTFY_PASSWORD", ""),
        help="Ntfy password (optional). For authenticated ntfy servers.",
    )
    buy_parser.add_argument(
        "--filename",
        type=str,
        default=os.environ.get("BTB_FILENAME", "default"),
        help="filename (optional).",
    )
    buy_parser.add_argument(
        "--https_proxys",
        type=str,
        default=os.environ.get("BTB_HTTPS_PROXYS", "none"),
        help="like none,http://127.0.0.1:8080",
    )
    buy_parser.add_argument(
        "--terminal_ui",
        type=str,
        default="网页",
        help="server name",
    )
    # `--worker` 子命令
    worker_parser = subparsers.add_parser("worker", help="Start the ticket worker ui")  # noqa: F841
    worker_parser.add_argument(
        "--master",
        type=str,
        default=os.environ.get("BTB_MASTER", ""),
        help="master url, like http://127.0.0.1:7890",
    )
    worker_parser.add_argument(
        "--self_ip",
        type=str,
        default=os.environ.get("BTB_SELF_IP", "127.0.0.1"),
        help="the ip that master note can access, like 127.0.0.1",
    )
    worker_parser.add_argument(
        "--https_proxys",
        type=str,
        default=os.environ.get("BTB_HTTPS_PROXYS", "none"),
    )
    parser.add_argument(
        "--port",
        type=int,
        help="server port",
    )
    parser.add_argument(
        "--server_name",
        type=str,
        default=os.environ.get("BTB_SERVER_NAME", "127.0.0.1"),
        help="server name",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        default=get_env_default("SHARE", False, lambda x: str(x).lower() == "true"),
        help="create a public link",
    )

    args = parser.parse_args()
    if args.command == "buy":
        from app_cmd.buy import buy_cmd

        buy_cmd(args=args)
    elif args.command == "worker":
        from app_cmd.worker import worker_cmd

        worker_cmd(args=args)
    else:
        from app_cmd.ticker import ticker_cmd

        ticker_cmd(args=args)


if __name__ == "__main__":
    main()
