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


def format_network_speed(bps: float) -> str:
    """Format bits-per-second as Mbps or Gbps."""
    if bps <= 0:
        return "0 Mbps"
    mbps = bps / 1_000_000
    if mbps >= 1000:
        return f"{mbps / 1000:.2f} Gbps"
    if mbps >= 100:
        return f"{mbps:.0f} Mbps"
    if mbps >= 10:
        return f"{mbps:.1f} Mbps"
    return f"{mbps:.2f} Mbps"


def format_network(group: AppGroup, *, estimated: bool = False) -> str:
    suffix = "~" if estimated else ""
    if group.net_down_bps > 0 or group.net_up_bps > 0:
        return (
            f"↓{format_network_speed(group.net_down_bps)}{suffix} "
            f"↑{format_network_speed(group.net_up_bps)}{suffix}"
        )
    if group.socket_count > 0:
        return f"{group.socket_count} sock"
    return "-"
