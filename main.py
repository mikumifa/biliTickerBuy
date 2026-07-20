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
        "--config-file" if arg in {"-cf", "--config-file"} else arg for arg in argv
    ]

    argv = normalized
    if not argv:
        return ["ui"]

    first = argv[0]
    if first in {"buy", "ui", "-h", "--help"}:
        return argv

    return ["ui", *argv]


def _explicit_cli_flags(argv: list[str]) -> set[str]:
    """从命令行 argv 中提取用户显式传入的 flag 集合（形如 --interval / --xxx=y）。"""
    flags: set[str] = set()
    for arg in argv:
        if arg.startswith("--"):
            flags.add(arg.split("=", 1)[0])
    return flags


def main() -> None:
    argv = _normalize_argv(sys.argv[1:])
    command = tyro.cli(CliCommand, args=argv)  # type: ignore
    if isinstance(command, BuyCliArgs):
        # buy(无头)命令下用环境变量回填未显式传入的字段：CLI > env(BTB_*) > 默认值
        command = command.merge_env(_explicit_cli_flags(argv))
        buy_cmd(command)
        return
    ticker_cmd(command)


if __name__ == "__main__":
    main()
