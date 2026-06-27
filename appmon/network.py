"""Network usage collection via cgroup accounting and socket counts."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from appmon.proc import PROC_ROOT, _read_text

CGROUP_ROOT = Path("/sys/fs/cgroup")


@dataclass(frozen=True, slots=True)
class NetworkSample:
    rx_bytes: int
    tx_bytes: int
    socket_count: int


def _read_int(path: Path) -> int:
    text = _read_text(path)
    if not text:
        return 0
    try:
        return int(text.strip())
    except ValueError:
        return 0


@lru_cache(maxsize=256)
def _cgroup_has_ip_accounting(cgroup_path: str) -> bool:
    if not cgroup_path:
        return False
    base = CGROUP_ROOT / cgroup_path.lstrip("/")
    return (base / "ip-ingress.bytes").is_file() and (base / "ip-egress.bytes").is_file()


def read_cgroup_network_bytes(cgroup_path: str) -> tuple[int, int]:
    if not cgroup_path or not _cgroup_has_ip_accounting(cgroup_path):
        return 0, 0
    base = CGROUP_ROOT / cgroup_path.lstrip("/")
    return _read_int(base / "ip-ingress.bytes"), _read_int(base / "ip-egress.bytes")


def read_socket_count(pid: int) -> int:
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
