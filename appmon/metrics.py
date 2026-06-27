"""Aggregate per-process samples into per-application metrics."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from appmon.grouping import GroupKey, build_parent_exe_index, resolve_group
from appmon.proc import CLK_TCK, ProcessInfo, collect_process, list_pids, read_meminfo


@dataclass(slots=True)
class ProcessSample:
    pid: int
    comm: str
    pss_bytes: int
    cpu_percent: float


@dataclass(slots=True)
class AppGroup:
    key: str
    display_name: str
    source: str
    pss_bytes: int = 0
    cpu_percent: float = 0.0
    process_count: int = 0
    processes: list[ProcessSample] = field(default_factory=list)


@dataclass(slots=True)
class SystemSnapshot:
    groups: list[AppGroup]
    total_mem_bytes: int
    available_mem_bytes: int
    used_mem_bytes: int
    total_cpu_percent: float
    pss_fallback: bool = False


class MetricsCollector:
    def __init__(self) -> None:
        self._prev_ticks: dict[int, tuple[int, int]] = {}
        self._prev_time: float | None = None
        self._cpu_count = os.cpu_count() or 1
        self._pss_fallback = False

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

    def sample(self) -> SystemSnapshot:
        now = time.monotonic()
        elapsed = 0.0 if self._prev_time is None else now - self._prev_time
        self._prev_time = now

        processes: list[ProcessInfo] = []
        for pid in list_pids():
            info = collect_process(pid)
            if info is not None:
                processes.append(info)

        parent_exe = build_parent_exe_index(processes)
        grouped: dict[str, AppGroup] = {}

        for process in processes:
            group_key: GroupKey = resolve_group(process, parent_exe)
            cpu_pct = self._cpu_percent(process.pid, process.utime, process.stime, elapsed)
            self._prev_ticks[process.pid] = (process.utime, process.stime)

            if group_key.key not in grouped:
                grouped[group_key.key] = AppGroup(
                    key=group_key.key,
                    display_name=group_key.display_name,
                    source=group_key.source.value,
                )
            app_group = grouped[group_key.key]
            app_group.pss_bytes += process.pss_bytes
            app_group.cpu_percent += cpu_pct
            app_group.process_count += 1
            app_group.processes.append(
                ProcessSample(
                    pid=process.pid,
                    comm=process.comm,
                    pss_bytes=process.pss_bytes,
                    cpu_percent=cpu_pct,
                )
            )

        total_mem, available_mem = read_meminfo()
        used_mem = max(total_mem - available_mem, 0)
        groups = sorted(grouped.values(), key=lambda g: g.pss_bytes, reverse=True)
        total_cpu = sum(group.cpu_percent for group in groups)

        return SystemSnapshot(
            groups=groups,
            total_mem_bytes=total_mem,
            available_mem_bytes=available_mem,
            used_mem_bytes=used_mem,
            total_cpu_percent=min(total_cpu, 100.0 * self._cpu_count),
            pss_fallback=self._pss_fallback,
        )
