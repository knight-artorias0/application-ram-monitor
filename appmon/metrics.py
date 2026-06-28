"""Aggregate per-process samples into per-application metrics."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from appmon.gpu import GpuProcessStats, nvidia_available, sample_gpu_by_pid, sample_total_gpu_util
from appmon.grouping import GroupKey, build_parent_exe_index, resolve_group
from appmon.network import (
    SocketByteTotals,
    cgroup_has_ip_accounting,
    read_cgroup_network_bytes,
    read_socket_bytes_by_pid,
    read_socket_count,
    read_system_network_totals,
)
from appmon.proc import CLK_TCK, ProcessInfo, collect_process, list_pids, read_meminfo


@dataclass(slots=True)
class ProcessSample:
    pid: int
    comm: str
    pss_bytes: int
    cpu_percent: float
    gpu_percent: float = 0.0
    gpu_mem_bytes: int = 0
    net_down_bps: float = 0.0
    net_up_bps: float = 0.0
    socket_count: int = 0


@dataclass(slots=True)
class AppGroup:
    key: str
    display_name: str
    source: str
    pss_bytes: int = 0
    cpu_percent: float = 0.0
    gpu_percent: float = 0.0
    gpu_mem_bytes: int = 0
    net_down_bps: float = 0.0
    net_up_bps: float = 0.0
    socket_count: int = 0
    process_count: int = 0
    processes: list[ProcessSample] = field(default_factory=list)


@dataclass(slots=True)
class SystemSnapshot:
    groups: list[AppGroup]
    total_mem_bytes: int
    available_mem_bytes: int
    used_mem_bytes: int
    total_cpu_percent: float
    total_gpu_percent: float
    total_net_down_bps: float
    total_net_up_bps: float
    gpu_available: bool
    network_accounting: bool
    network_estimated: bool
    pss_fallback: bool = False


class MetricsCollector:
    def __init__(self) -> None:
        self._prev_ticks: dict[int, tuple[int, int]] = {}
        self._prev_cgroup_net: dict[str, tuple[int, int]] = {}
        self._prev_socket_net: dict[int, tuple[int, int]] = {}
        self._prev_system_net: tuple[int, int] | None = None
        self._prev_time: float | None = None
        self._cpu_count = os.cpu_count() or 1
        self._pss_fallback = False
        self._network_accounting = False
        self._network_estimated = False

    def _cpu_percent(
        self,
        pid: int,
        utime: int,
        stime: int,
        elapsed: float,
    ) -> float:
        prev = self._prev_ticks.get(pid)
        if prev is None or elapsed <= 0:
            return 0.0
        prev_utime, prev_stime = prev
        delta_ticks = (utime - prev_utime) + (stime - prev_stime)
        if delta_ticks < 0:
            return 0.0
        cpu_seconds = delta_ticks / CLK_TCK
        return (cpu_seconds / elapsed) * 100.0 / self._cpu_count

    def _socket_rates(
        self,
        pid: int,
        totals: SocketByteTotals,
        elapsed: float,
    ) -> tuple[float, float, bool]:
        current = (totals.rx_bytes, totals.tx_bytes)
        prev = self._prev_socket_net.get(pid)
        self._prev_socket_net[pid] = current
        if prev is None or elapsed <= 0:
            return 0.0, 0.0, False
        prev_rx, prev_tx = prev
        down_bps = max(current[0] - prev_rx, 0) * 8 / elapsed
        up_bps = max(current[1] - prev_tx, 0) * 8 / elapsed
        if down_bps > 0 or up_bps > 0:
            return down_bps, up_bps, True
        return 0.0, 0.0, current != prev

    def _cgroup_rates(
        self,
        cgroup_path: str,
        elapsed: float,
    ) -> tuple[float, float, bool]:
        rx_bytes, tx_bytes = read_cgroup_network_bytes(cgroup_path)
        if not (rx_bytes or tx_bytes or cgroup_has_ip_accounting(cgroup_path)):
            return 0.0, 0.0, False
        self._network_accounting = True
        prev = self._prev_cgroup_net.get(cgroup_path)
        self._prev_cgroup_net[cgroup_path] = (rx_bytes, tx_bytes)
        if prev is None or elapsed <= 0:
            return 0.0, 0.0, True
        prev_rx, prev_tx = prev
        down_bps = max(rx_bytes - prev_rx, 0) * 8 / elapsed
        up_bps = max(tx_bytes - prev_tx, 0) * 8 / elapsed
        return down_bps, up_bps, True

    def sample(self) -> SystemSnapshot:
        now = time.monotonic()
        elapsed = 0.0 if self._prev_time is None else now - self._prev_time
        self._prev_time = now
        self._network_accounting = False
        self._network_estimated = False

        gpu_by_pid: dict[int, GpuProcessStats] = {}
        if nvidia_available():
            gpu_by_pid = sample_gpu_by_pid()

        socket_bytes = read_socket_bytes_by_pid()
        pid_net_rates: dict[int, tuple[float, float]] = {}
        socket_tracking = False
        for pid, totals in socket_bytes.items():
            down_bps, up_bps, has_data = self._socket_rates(pid, totals, elapsed)
            if has_data:
                socket_tracking = True
            pid_net_rates[pid] = (down_bps, up_bps)

        processes: list[ProcessInfo] = []
        for pid in list_pids():
            info = collect_process(pid)
            if info is not None:
                processes.append(info)

        parent_exe = build_parent_exe_index(processes)
        grouped: dict[str, AppGroup] = {}
        cgroup_paths_by_group: dict[str, str] = {}

        for process in processes:
            group_key: GroupKey = resolve_group(process, parent_exe)
            cpu_pct = self._cpu_percent(process.pid, process.utime, process.stime, elapsed)
            self._prev_ticks[process.pid] = (process.utime, process.stime)

            gpu_stats = gpu_by_pid.get(process.pid)
            gpu_pct = gpu_stats.gpu_percent if gpu_stats else 0.0
            gpu_mem = gpu_stats.gpu_mem_bytes if gpu_stats else 0
            sockets = read_socket_count(process.pid)
            net_down, net_up = pid_net_rates.get(process.pid, (0.0, 0.0))

            if group_key.key not in grouped:
                grouped[group_key.key] = AppGroup(
                    key=group_key.key,
                    display_name=group_key.display_name,
                    source=group_key.source.value,
                )
                cgroup_paths_by_group[group_key.key] = process.cgroup_path
            elif process.cgroup_path and not cgroup_paths_by_group.get(group_key.key):
                cgroup_paths_by_group[group_key.key] = process.cgroup_path

            app_group = grouped[group_key.key]
            app_group.pss_bytes += process.pss_bytes
            app_group.cpu_percent += cpu_pct
            app_group.gpu_percent += gpu_pct
            app_group.gpu_mem_bytes += gpu_mem
            app_group.socket_count += sockets
            app_group.net_down_bps += net_down
            app_group.net_up_bps += net_up
            app_group.process_count += 1
            app_group.processes.append(
                ProcessSample(
                    pid=process.pid,
                    comm=process.comm,
                    pss_bytes=process.pss_bytes,
                    cpu_percent=cpu_pct,
                    gpu_percent=gpu_pct,
                    gpu_mem_bytes=gpu_mem,
                    net_down_bps=net_down,
                    net_up_bps=net_up,
                    socket_count=sockets,
                )
            )

        for group in grouped.values():
            cgroup_path = cgroup_paths_by_group.get(group.key, "")
            cgroup_down, cgroup_up, has_cgroup = self._cgroup_rates(cgroup_path, elapsed)
            if has_cgroup and (cgroup_down > 0 or cgroup_up > 0):
                group.net_down_bps = cgroup_down
                group.net_up_bps = cgroup_up
                for proc in group.processes:
                    proc.net_down_bps = cgroup_down / max(group.process_count, 1)
                    proc.net_up_bps = cgroup_up / max(group.process_count, 1)

        total_mem, available_mem = read_meminfo()
        used_mem = max(total_mem - available_mem, 0)
        groups = list(grouped.values())
        total_cpu = sum(group.cpu_percent for group in groups)
        per_pid_gpu = sum(group.gpu_percent for group in groups)
        total_gpu = per_pid_gpu if per_pid_gpu > 0 else sample_total_gpu_util()
        total_down = sum(group.net_down_bps for group in groups)
        total_up = sum(group.net_up_bps for group in groups)

        system_rx, system_tx = read_system_network_totals()
        prev_system = self._prev_system_net
        self._prev_system_net = (system_rx, system_tx)
        system_down = 0.0
        system_up = 0.0
        if prev_system is not None and elapsed > 0:
            system_down = max(system_rx - prev_system[0], 0) * 8 / elapsed
            system_up = max(system_tx - prev_system[1], 0) * 8 / elapsed

        if socket_tracking:
            self._network_estimated = False
            if total_down == 0 and total_up == 0:
                total_down = system_down
                total_up = system_up
        elif not self._network_accounting:
            total_down = system_down
            total_up = system_up
            if elapsed > 0 and (system_down > 0 or system_up > 0):
                total_sockets = sum(group.socket_count for group in groups)
                if total_sockets > 0:
                    for group in groups:
                        share = group.socket_count / total_sockets
                        group.net_down_bps = system_down * share
                        group.net_up_bps = system_up * share
                        for proc in group.processes:
                            proc.net_down_bps = group.net_down_bps / max(group.process_count, 1)
                            proc.net_up_bps = group.net_up_bps / max(group.process_count, 1)
                    self._network_estimated = True

        return SystemSnapshot(
            groups=groups,
            total_mem_bytes=total_mem,
            available_mem_bytes=available_mem,
            used_mem_bytes=used_mem,
            total_cpu_percent=min(total_cpu, 100.0 * self._cpu_count),
            total_gpu_percent=min(total_gpu, 100.0),
            total_net_down_bps=total_down,
            total_net_up_bps=total_up,
            gpu_available=nvidia_available(),
            network_accounting=self._network_accounting,
            network_estimated=self._network_estimated,
            pss_fallback=self._pss_fallback,
        )
