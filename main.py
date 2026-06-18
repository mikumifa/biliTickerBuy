from __future__ import annotations

import sys
import warnings
from typing import Annotated

import tyro
from starlette.exceptions import StarletteDeprecationWarning
from app_cmd.buy import buy_cmd
from app_cmd.cli_args import BuyCliArgs, TickerCliArgs
from app_cmd.ticker import ticker_cmd

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
CliCommand = BuyCommand | UiCommand


def _normalize_argv(argv: list[str]) -> list[str]:
    normalized = [
        "--config-file" if arg in {"-cf", "--config-fileme"} else arg for arg in argv
    ]

    argv = normalized
    if not argv:
        return ["ui"]

    first = argv[0]
    if first in {"buy", "ui", "-h", "--help"}:
        return argv

    return ["ui", *argv]


def main() -> None:
    command = tyro.cli(CliCommand, args=_normalize_argv(sys.argv[1:]))  # type: ignore
    if isinstance(command, BuyCliArgs):
        buy_cmd(command)
        return
    ticker_cmd(command)


if __name__ == "__main__":
    main()
