from __future__ import annotations

import sys
import warnings
from typing import Annotated

import tyro
from starlette.exceptions import StarletteDeprecationWarning
from app_cmd.cli_args import BuyCliArgs, BwsCliArgs, TickerCliArgs

warnings.filterwarnings(
    "ignore",
    message=r".*HTTP_422_UNPROCESSABLE_ENTITY.*",
    category=StarletteDeprecationWarning,
    module=r"gradio\.routes",
)
BuyCommand = Annotated[
    BuyCliArgs,
    tyro.conf.subcommand(name="buy", prefix_name=False),
]
UiCommand = Annotated[
    TickerCliArgs,
    tyro.conf.subcommand(name="ui", prefix_name=False),
]
BwsCommand = Annotated[
    BwsCliArgs,
    tyro.conf.subcommand(name="bws", prefix_name=False),
]
CliCommand = BuyCommand | UiCommand | BwsCommand


def _normalize_argv(argv: list[str]) -> list[str]:
    normalized = [
        "--config-file" if arg in {"-cf", "--config-file"} else arg for arg in argv
    ]

    argv = normalized
    if not argv:
        return ["ui"]

    first = argv[0]
    if first in {"buy", "ui", "bws", "-h", "--help"}:
        return argv

    return ["ui", *argv]


def main() -> None:
    command = tyro.cli(CliCommand, args=_normalize_argv(sys.argv[1:]))  # type: ignore
    if isinstance(command, BuyCliArgs):
        from app_cmd.buy import buy_cmd

        buy_cmd(command)
        return
    if isinstance(command, BwsCliArgs):
        from app_cmd.bws import bws_cmd

        bws_cmd(command)
        return
    from app_cmd.ticker import ticker_cmd

    ticker_cmd(command)


if __name__ == "__main__":
    main()
