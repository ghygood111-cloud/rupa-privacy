"""Read-only application resources and writable local GUI paths."""

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    if is_frozen():
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[1]


def resource_path(relative_path) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Application resource paths must be relative and contained")
    return resource_root() / relative


def user_data_root() -> Path:
    if not is_frozen():
        return resource_root() / "demo"
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base.resolve() / "RUPA"
