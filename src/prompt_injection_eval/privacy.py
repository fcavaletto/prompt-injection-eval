"""Redact local machine details before they are written to artifacts."""

from __future__ import annotations

import platform
import re
import sys
from pathlib import Path

_HOME_PATH = re.compile(r"(?:/Users|/home)/[^/\s]+")


def sanitize_text(value: str) -> str:
    """Remove home-directory paths from an exception or provider message."""
    home = str(Path.home())
    if home and home in value:
        value = value.replace(home, "~")
    return _HOME_PATH.sub("~", value)


def python_version() -> str:
    return sys.version.split()[0]


def platform_summary() -> str:
    """Return a general OS and architecture summary without hostname or serial."""
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin":
        mac_version = platform.mac_ver()[0] or "unknown"
        return f"macOS {mac_version} {machine}"
    return f"{system} {platform.release()} {machine}"


def display_path(path: Path) -> str:
    """Prefer a cwd-relative path so artifacts do not store home directories."""
    resolved = path.expanduser().resolve()
    cwd = Path.cwd().resolve()
    try:
        return str(resolved.relative_to(cwd))
    except ValueError:
        return path.name
