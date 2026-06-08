"""Application version helpers."""

from importlib.metadata import PackageNotFoundError, version

__version__ = "2.14.16"


def get_app_version() -> str:
    """Return the installed package version, falling back to the source constant."""
    try:
        return version("bilitickerbuy")
    except PackageNotFoundError:
        return __version__
