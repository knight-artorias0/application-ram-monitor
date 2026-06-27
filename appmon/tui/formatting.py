"""Shared formatting helpers for the TUI."""

from __future__ import annotations

from appmon.metrics import AppGroup


def format_bytes(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "0 B"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(num_bytes)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def format_percent(value: float) -> str:
    return f"{value:5.1f}%"


def format_bitrate(bps: float) -> str:
    if bps <= 0:
        return "0 bps"
    units = ("bps", "Kbps", "Mbps", "Gbps")
    value = float(bps)
    unit = units[0]
    for unit in units:
        if value < 1000 or unit == units[-1]:
            break
        value /= 1000
    if unit == "bps":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def format_network(group: AppGroup, accounting: bool) -> str:
    if accounting:
        return f"↓{format_bitrate(group.net_down_bps)} ↑{format_bitrate(group.net_up_bps)}"
    if group.socket_count > 0:
        return f"{group.socket_count} sock"
    return "-"
