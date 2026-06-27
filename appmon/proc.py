"""Low-level /proc filesystem readers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROC_ROOT = Path("/proc")
CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


@dataclass(frozen=True, slots=True)
class ProcessStat:
    pid: int
    comm: str
    utime: int
    stime: int
    rss_pages: int


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    comm: str
    exe: str | None
    cmdline: str
    cgroup_path: str
    pss_bytes: int
    rss_bytes: int
    utime: int
    stime: int
    ppid: int


def list_pids() -> list[int]:
    pids: list[int] = []
    try:
        entries = PROC_ROOT.iterdir()
    except OSError:
        return pids
    for entry in entries:
        if entry.name.isdigit():
            pids.append(int(entry.name))
    return pids


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def read_cgroup(pid: int) -> str:
    text = _read_text(PROC_ROOT / str(pid) / "cgroup")
    if not text:
        return ""
    for line in text.splitlines():
        # cgroup v2 unified hierarchy: 0::/path
        if line.startswith("0::"):
            return line[3:].strip()
    # cgroup v1 fallback: pick first non-empty controller path
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[2]:
            return parts[2].strip()
    return ""


def read_stat(pid: int) -> ProcessStat | None:
    text = _read_text(PROC_ROOT / str(pid) / "stat")
    if not text:
        return None
    # comm may contain spaces: (name)
    open_paren = text.find("(")
    close_paren = text.find(")", open_paren + 1)
    if open_paren == -1 or close_paren == -1:
        return None
    comm = text[open_paren + 1 : close_paren]
    rest = text[close_paren + 2 :].split()
    if len(rest) < 20:
        return None
    try:
        return ProcessStat(
            pid=pid,
            comm=comm,
            utime=int(rest[11]),
            stime=int(rest[12]),
            rss_pages=int(rest[21]),
        )
    except (ValueError, IndexError):
        return None


def read_ppid(pid: int) -> int:
    text = _read_text(PROC_ROOT / str(pid) / "status")
    if not text:
        return 0
    for line in text.splitlines():
        if line.startswith("PPid:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return 0
    return 0


def read_exe(pid: int) -> str | None:
    exe_path = PROC_ROOT / str(pid) / "exe"
    try:
        return os.readlink(exe_path)
    except OSError:
        return None


def read_cmdline(pid: int) -> str:
    text = _read_text(PROC_ROOT / str(pid) / "cmdline")
    if not text:
        return ""
    parts = [part for part in text.split("\0") if part]
    return " ".join(parts)


def read_memory(pid: int) -> tuple[int, int]:
    """Return (pss_bytes, rss_bytes). Falls back to RSS when PSS is unavailable."""
    rollup = PROC_ROOT / str(pid) / "smaps_rollup"
    text = _read_text(rollup)
    pss = 0
    rss = 0
    if text:
        for line in text.splitlines():
            if line.startswith("Pss:"):
                pss = int(line.split()[1]) * 1024
            elif line.startswith("Rss:"):
                rss = int(line.split()[1]) * 1024
    if pss or rss:
        return pss or rss, rss or pss

    stat = read_stat(pid)
    if stat is None:
        return 0, 0
    page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
    rss = stat.rss_pages * page_size
    return rss, rss


def collect_process(pid: int) -> ProcessInfo | None:
    stat = read_stat(pid)
    if stat is None:
        return None
    pss, rss = read_memory(pid)
    return ProcessInfo(
        pid=pid,
        comm=stat.comm,
        exe=read_exe(pid),
        cmdline=read_cmdline(pid),
        cgroup_path=read_cgroup(pid),
        pss_bytes=pss,
        rss_bytes=rss,
        utime=stat.utime,
        stime=stat.stime,
        ppid=read_ppid(pid),
    )


def read_meminfo() -> tuple[int, int]:
    """Return (total_bytes, available_bytes)."""
    text = _read_text(PROC_ROOT / "meminfo")
    if not text:
        return 0, 0
    total = 0
    available = 0
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            total = int(line.split()[1]) * 1024
        elif line.startswith("MemAvailable:"):
            available = int(line.split()[1]) * 1024
    return total, available
