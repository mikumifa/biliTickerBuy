#!/usr/bin/env python3
"""Ensure git tag and pyproject version are aligned for releases."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = ROOT / "pyproject.toml"
TAG_PREFIX_RE = re.compile(r"^refs/tags/")


def normalize_tag(raw_tag: str) -> str:
    tag = TAG_PREFIX_RE.sub("", raw_tag.strip())
    if tag.startswith("v"):
        tag = tag[1:]
    return tag


def read_project_version() -> str:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    try:
        return data["project"]["version"]
    except KeyError as exc:
        raise RuntimeError("Cannot find [project].version in pyproject.toml") from exc


def main() -> int:
    raw_tag = os.getenv("GITHUB_REF_NAME") or os.getenv("GITHUB_REF")
    if not raw_tag:
        print("ERROR: Missing GITHUB_REF_NAME/GITHUB_REF; cannot validate release tag.")
        return 2

    tag_version = normalize_tag(raw_tag)
    project_version = read_project_version().strip()

    if tag_version != project_version:
        print(
            "ERROR: Version mismatch. "
            f"git tag is '{tag_version}', but pyproject.toml is '{project_version}'."
        )
        print("Hint: bump [project].version first, then create/push the matching tag.")
        return 1

    print(f"Version check passed: tag '{tag_version}' matches pyproject version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
