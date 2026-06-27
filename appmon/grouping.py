"""Tiered process grouping: cgroup app ID, flatpak, then executable name."""

from __future__ import annotations

import os
from dataclasses import dataclass

from appmon.cgroup import GroupSource, parse_cgroup_path
from appmon.desktop import humanize_app_id
from appmon.proc import ProcessInfo

# Merge browser/content/helper processes that share no cgroup with their parent app.
COMM_ALIASES: dict[str, str] = {
    "web content": "firefox",
    "webextensions": "firefox",
    "socket process": "firefox",
    "privileged cont": "firefox",
    "utility process": "firefox",
    "renderer": "chrome",
    "gpu-process": "chrome",
    "zygote": "chrome",
}

EXE_ALIASES: dict[str, str] = {
    "chrome": "google-chrome",
    "chromium": "chromium",
    "code-oss": "code",
    "electron": "electron",
    "firefox": "firefox",
    "firefox-bin": "firefox",
}


@dataclass(frozen=True, slots=True)
class GroupKey:
    key: str
    source: GroupSource
    display_name: str


def _basename_exe(exe: str | None) -> str:
    if not exe:
        return ""
    return os.path.basename(exe)


def _exe_group_key(process: ProcessInfo) -> str:
    exe_name = _basename_exe(process.exe)
    if exe_name:
        return EXE_ALIASES.get(exe_name, exe_name)
    if process.cmdline:
        return os.path.basename(process.cmdline.split()[0])
    comm = process.comm.lower()
    return COMM_ALIASES.get(comm, comm or f"pid-{process.pid}")


def resolve_group(process: ProcessInfo, parent_exe_by_pid: dict[int, str]) -> GroupKey:
    cgroup_match = parse_cgroup_path(process.cgroup_path)
    if cgroup_match is not None:
        return GroupKey(
            key=cgroup_match.app_id,
            source=cgroup_match.source,
            display_name=humanize_app_id(cgroup_match.app_id),
        )

    comm = process.comm.lower()
    if comm in COMM_ALIASES:
        parent_exe = parent_exe_by_pid.get(process.ppid, "")
        parent_key = EXE_ALIASES.get(_basename_exe(parent_exe), _basename_exe(parent_exe))
        if parent_key:
            return GroupKey(
                key=parent_key,
                source=GroupSource.EXE,
                display_name=humanize_app_id(parent_key),
            )

    exe_key = _exe_group_key(process)
    return GroupKey(
        key=exe_key,
        source=GroupSource.EXE,
        display_name=humanize_app_id(exe_key),
    )


def build_parent_exe_index(processes: list[ProcessInfo]) -> dict[int, str]:
    return {process.pid: process.exe or "" for process in processes}
