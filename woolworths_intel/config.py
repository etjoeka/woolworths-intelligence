"""Configuration loading for Coles Intelligence."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Load config.yaml (or a custom path) and return the parsed mapping."""
    cfg_path = Path(path) if path else PACKAGE_ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def resolve_path(value: str, base: Path | None = None) -> Path:
    """Resolve a config path relative to the package root unless absolute."""
    p = Path(value)
    if p.is_absolute():
        return p
    return (base or PACKAGE_ROOT) / p
