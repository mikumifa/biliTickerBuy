from __future__ import annotations

import sys

import tyro

from app_cmd.buy import buy_cmd
from app_cmd.cli_args import BuyCliArgs, TickerCliArgs
from app_cmd.ticker import ticker_cmd


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        ticker_cmd(TickerCliArgs())
        return

    if argv[0] == "buy":
        buy_cmd(tyro.cli(BuyCliArgs, args=argv[1:]))
        return

    if argv[0] == "ui":
        ticker_cmd(tyro.cli(TickerCliArgs, args=argv[1:]))
        return

    ticker_cmd(tyro.cli(TickerCliArgs, args=argv))


if __name__ == "__main__":
    main()
