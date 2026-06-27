"""Resolve application IDs to human-readable names via .desktop files."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

DESKTOP_DIRS = (
    Path("/usr/local/share/applications"),
    Path("/usr/share/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/applications",
    Path.home() / ".local/share/flatpak/exports/share/applications",
)


def _parse_desktop_name(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("Name="):
            return line.split("=", 1)[1].strip()
    return None


@lru_cache(maxsize=1)
def _desktop_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for directory in DESKTOP_DIRS:
        if not directory.is_dir():
            continue
        try:
            entries = directory.iterdir()
        except OSError:
            continue
        for entry in entries:
            if not entry.suffix == ".desktop":
                continue
            stem = entry.stem
            if stem in index:
                continue
            name = _parse_desktop_name(entry)
            if name:
                index[stem] = name
    return index


def lookup_desktop_name(app_id: str) -> str | None:
    index = _desktop_index()
    if app_id in index:
        return index[app_id]
    # Reverse-DNS ids often map directly to desktop stems.
    short = app_id.split(".")[-1]
    for key, value in index.items():
        if key.endswith(short) or key == short:
            return value
    return None


def humanize_app_id(app_id: str) -> str:
    desktop = lookup_desktop_name(app_id)
    if desktop:
        return desktop
    # code-oss -> Code Oss, org.mozilla.firefox -> Firefox
    token = app_id.split(".")[-1]
    return token.replace("-", " ").replace("_", " ").title()
