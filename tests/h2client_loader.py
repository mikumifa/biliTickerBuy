from __future__ import annotations

import importlib
import importlib.machinery
import sys
import types
from pathlib import Path


PACKAGE_NAME = "_btb_h2client"
H2CLIENT_DIR = Path(__file__).resolve().parents[1] / "util" / "h2client"


def load_h2client_module(name: str):
    if PACKAGE_NAME not in sys.modules:
        package = types.ModuleType(PACKAGE_NAME)
        package.__path__ = [str(H2CLIENT_DIR)]
        package.__package__ = PACKAGE_NAME
        package.__spec__ = importlib.machinery.ModuleSpec(
            PACKAGE_NAME,
            loader=None,
            is_package=True,
        )
        package.__spec__.submodule_search_locations = [str(H2CLIENT_DIR)]
        sys.modules[PACKAGE_NAME] = package

    return importlib.import_module(f"{PACKAGE_NAME}.{name}")
