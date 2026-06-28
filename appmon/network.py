"""Per-process network usage via socket byte counters."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from appmon.proc import PROC_ROOT, list_pids

BYTES_SENT_RE = re.compile(r"bytes_sent:(\d+)")
BYTES_RECEIVED_RE = re.compile(r"bytes_received:(\d+)")
PID_RE = re.compile(r"pid=(\d+)")


@dataclass(frozen=True, slots=True)
class SocketByteTotals:
    rx_bytes: int
    tx_bytes: int


def _ss_path() -> str | None:
    return shutil.which("ss")


def _build_inode_pid_map() -> dict[int, int]:
    mapping: dict[int, int] = {}
    for pid in list_pids():
        fd_dir = PROC_ROOT / str(pid) / "fd"
        try:
            fds = fd_dir.iterdir()
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if not target.startswith("socket:["):
                continue
            inode_text = target[8:-1]
            if inode_text.isdigit():
                mapping[int(inode_text)] = pid
    return mapping


def _parse_ss_output(output: str) -> dict[int, SocketByteTotals]:
    totals: dict[int, list[int]] = {}
    current_pids: list[int] = []

    for line in output.splitlines():
        if not line:
            continue
        if not line.startswith(" "):
            current_pids = [int(match) for match in PID_RE.findall(line)]
            payload = line
        else:
            payload = line

        if not current_pids:
            continue

        sent_match = BYTES_SENT_RE.search(payload)
        received_match = BYTES_RECEIVED_RE.search(payload)
        if not sent_match and not received_match:
            continue

        sent = int(sent_match.group(1)) if sent_match else 0
        received = int(received_match.group(1)) if received_match else 0
        for pid in current_pids:
            bucket = totals.setdefault(pid, [0, 0])
            bucket[0] += received
            bucket[1] += sent

    return {
        pid: SocketByteTotals(rx_bytes=values[0], tx_bytes=values[1])
        for pid, values in totals.items()
    }


def read_socket_bytes_by_pid() -> dict[int, SocketByteTotals]:
    """Read cumulative socket RX/TX byte counters per PID using ss."""
    ss = _ss_path()
    if ss is None:
        return {}

    try:
        result = subprocess.run(
            [ss, "-H", "-tunip"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}

    if result.returncode != 0 or not result.stdout.strip():
        try:
            result = subprocess.run(
                [ss, "-H", "-tuni"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}

    if result.returncode != 0:
        return {}

    stats = _parse_ss_output(result.stdout)
    if stats:
        return stats

    # Fallback when ss output lacks byte counters: count sockets only.
    inode_map = _build_inode_pid_map()
    for line in result.stdout.splitlines():
        for pid in PID_RE.findall(line):
            pid_int = int(pid)
            stats.setdefault(pid_int, SocketByteTotals(0, 0))
    _ = inode_map
    return stats


def read_system_network_totals() -> tuple[int, int]:
    rx = 0
    tx = 0
    net_dir = Path("/sys/class/net")
    try:
        entries = net_dir.iterdir()
    except OSError:
        return 0, 0
    for entry in entries:
        if entry.name == "lo":
            continue
        rx += _read_int(entry / "statistics" / "rx_bytes")
        tx += _read_int(entry / "statistics" / "tx_bytes")
    return rx, tx


def _read_int(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def read_socket_count(pid: int) -> int:
    from appmon.proc import _read_text

    text = _read_text(PROC_ROOT / str(pid) / "net" / "sockstat")
    if not text:
        return 0
    tcp_inuse = 0
    udp_inuse = 0
    for line in text.splitlines():
        if line.startswith("TCP:"):
            parts = line.split()
            if len(parts) > 2 and parts[1] == "inuse":
                try:
                    tcp_inuse = int(parts[2])
                except ValueError:
                    pass
        elif line.startswith("UDP:"):
            parts = line.split()
            if len(parts) > 2 and parts[1] == "inuse":
                try:
                    udp_inuse = int(parts[2])
                except ValueError:
                    pass
    return tcp_inuse + udp_inuse


def _cgroup_candidates(cgroup_path: str) -> list[Path]:
    if not cgroup_path:
        return []
    parts = [part for part in cgroup_path.strip("/").split("/") if part]
    return [Path("/sys/fs/cgroup") / "/".join(parts[:end]) for end in range(len(parts), 0, -1)]


def cgroup_has_ip_accounting(cgroup_path: str) -> bool:
    for base in _cgroup_candidates(cgroup_path):
        if (base / "ip-ingress.bytes").is_file() and (base / "ip-egress.bytes").is_file():
            return True
    return False


def read_cgroup_network_bytes(cgroup_path: str) -> tuple[int, int]:
    for base in _cgroup_candidates(cgroup_path):
        ingress = base / "ip-ingress.bytes"
        egress = base / "ip-egress.bytes"
        if ingress.is_file() and egress.is_file():
            return _read_int(ingress), _read_int(egress)
    return 0, 0
