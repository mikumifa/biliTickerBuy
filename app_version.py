"""Application version helpers."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import tomllib


def get_app_version() -> str:
    """Return the installed package version, falling back to pyproject.toml."""
    try:
        return version("bilitickerbuy")
    except PackageNotFoundError:
        pyproject_path = Path(__file__).resolve().with_name("pyproject.toml")
        with pyproject_path.open("rb") as fh:
            data = tomllib.load(fh)
        return str(data["project"]["version"])
