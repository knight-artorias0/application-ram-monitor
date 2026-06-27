"""Parse cgroup paths into application identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

UUID_SUFFIX_RE = re.compile(
    r"-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
INSTANCE_SUFFIX_RE = re.compile(r"-\d+$")
SCOPE_SUFFIX_RE = re.compile(r"\.(?:scope|service|slice)$")
SNAP_SCOPE_RE = re.compile(
    r"(?:^|/)(?:app-)?snap\.[0-9a-fA-F-]+\.([^.]+)\.([^.]+)\.scope$"
)


class GroupSource(str, Enum):
    CGROUP = "cgroup"
    FLATPAK = "flatpak"
    SNAP = "snap"
    EXE = "exe"


@dataclass(frozen=True, slots=True)
class CgroupMatch:
    app_id: str
    source: GroupSource


def _basename(path: str) -> str:
    return path.rstrip("/").split("/")[-1]


def _strip_scope_suffix(scope_name: str) -> str:
    name = SCOPE_SUFFIX_RE.sub("", scope_name)
    name = UUID_SUFFIX_RE.sub("", name)
    name = INSTANCE_SUFFIX_RE.sub("", name)
    return name


def _parse_scope_name(scope_name: str) -> CgroupMatch | None:
    if scope_name.startswith("app-flatpak-"):
        app_id = _strip_scope_suffix(scope_name[len("app-flatpak-") :])
        return CgroupMatch(app_id=app_id, source=GroupSource.FLATPAK)

    for prefix, source in (
        ("app-", GroupSource.CGROUP),
        ("apps-", GroupSource.CGROUP),
        ("flatpak-", GroupSource.FLATPAK),
        ("dbus-", GroupSource.CGROUP),
    ):
        if scope_name.startswith(prefix):
            app_id = _strip_scope_suffix(scope_name[len(prefix) :])
            if app_id:
                return CgroupMatch(app_id=app_id, source=source)
    return None


def parse_cgroup_path(cgroup_path: str) -> CgroupMatch | None:
    if not cgroup_path:
        return None

    snap_match = SNAP_SCOPE_RE.search(cgroup_path)
    if snap_match:
        package, app = snap_match.groups()
        return CgroupMatch(app_id=f"{package}.{app}", source=GroupSource.SNAP)

    scope_name = _basename(cgroup_path)
    parsed = _parse_scope_name(scope_name)
    if parsed is not None:
        return parsed

    if "/app.slice/" in cgroup_path:
        # Some systems nest scopes deeper than the basename parser expects.
        for part in reversed(cgroup_path.split("/")):
            parsed = _parse_scope_name(part)
            if parsed is not None:
                return parsed

    return None
