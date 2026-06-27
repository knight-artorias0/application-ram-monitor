"""NVIDIA GPU usage collection via nvidia-smi."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class GpuProcessStats:
    gpu_percent: float
    gpu_mem_bytes: int


@lru_cache(maxsize=1)
def _nvidia_smi_path() -> str | None:
    return shutil.which("nvidia-smi")


def nvidia_available() -> bool:
    return _nvidia_smi_path() is not None


def _run_nvidia_smi(*args: str) -> str:
    path = _nvidia_smi_path()
    if path is None:
        return ""
    try:
        result = subprocess.run(
            [path, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def sample_gpu_by_pid() -> dict[int, GpuProcessStats]:
    """Return per-PID GPU utilization and VRAM from nvidia-smi."""
    if not nvidia_available():
        return {}

    util_by_pid: dict[int, float] = {}
    pmon = _run_nvidia_smi("pmon", "-c", "1", "-s", "u")
    for line in pmon.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        # gpu pid type sm mem enc dec command...
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[1])
            sm = float(parts[3])
        except ValueError:
            continue
        util_by_pid[pid] = util_by_pid.get(pid, 0.0) + sm

    mem_by_pid: dict[int, int] = {}
    query = _run_nvidia_smi(
        "--query-compute-apps=pid,used_gpu_memory",
        "--format=csv,noheader,nounits",
    )
    for line in query.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
            mem_mib = float(parts[1])
        except ValueError:
            continue
        mem_by_pid[pid] = mem_by_pid.get(pid, 0) + int(mem_mib * 1024 * 1024)

    stats: dict[int, GpuProcessStats] = {}
    for pid in set(util_by_pid) | set(mem_by_pid):
        stats[pid] = GpuProcessStats(
            gpu_percent=util_by_pid.get(pid, 0.0),
            gpu_mem_bytes=mem_by_pid.get(pid, 0),
        )
    return stats
