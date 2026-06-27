"""NVIDIA GPU usage via bundled nvidia-ml-py, with nvidia-smi fallback."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache

_NVML_INITIALIZED = False
_NVML_AVAILABLE = False


@dataclass(frozen=True, slots=True)
class GpuProcessStats:
    gpu_percent: float
    gpu_mem_bytes: int


def _try_init_nvml() -> bool:
    global _NVML_INITIALIZED, _NVML_AVAILABLE
    if _NVML_INITIALIZED:
        return _NVML_AVAILABLE
    _NVML_INITIALIZED = True
    try:
        import pynvml  # type: ignore[import-untyped]  # nvidia-ml-py

        pynvml.nvmlInit()
        pynvml.nvmlDeviceGetCount()
        _NVML_AVAILABLE = True
    except Exception:
        _NVML_AVAILABLE = False
    return _NVML_AVAILABLE


@lru_cache(maxsize=1)
def _nvidia_smi_path() -> str | None:
    return shutil.which("nvidia-smi")


def nvidia_available() -> bool:
    return _try_init_nvml() or _nvidia_smi_path() is not None


def _merge_stat(
    stats: dict[int, GpuProcessStats],
    pid: int,
    *,
    gpu_percent: float | None = None,
    gpu_mem_bytes: int | None = None,
) -> None:
    current = stats.get(pid, GpuProcessStats(0.0, 0))
    stats[pid] = GpuProcessStats(
        gpu_percent=gpu_percent if gpu_percent is not None else current.gpu_percent,
        gpu_mem_bytes=gpu_mem_bytes if gpu_mem_bytes is not None else current.gpu_mem_bytes,
    )


def _sample_via_nvml() -> dict[int, GpuProcessStats]:
    import pynvml  # type: ignore[import-untyped]

    stats: dict[int, GpuProcessStats] = {}
    device_count = pynvml.nvmlDeviceGetCount()
    for index in range(device_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        for getter in (
            pynvml.nvmlDeviceGetComputeRunningProcesses,
            pynvml.nvmlDeviceGetGraphicsRunningProcesses,
        ):
            try:
                processes = getter(handle)
            except pynvml.NVMLError:
                continue
            for process in processes:
                if process.usedGpuMemory in (
                    None,
                    pynvml.NVML_VALUE_NOT_AVAILABLE,
                ):
                    continue
                _merge_stat(
                    stats,
                    process.pid,
                    gpu_mem_bytes=int(process.usedGpuMemory),
                )

        try:
            samples = pynvml.nvmlDeviceGetProcessUtilization(handle, 0)
        except (pynvml.NVMLError, AttributeError):
            continue
        for sample in samples:
            _merge_stat(
                stats,
                sample.pid,
                gpu_percent=float(sample.smUtil),
            )
    return stats


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


def _sample_via_nvidia_smi() -> dict[int, GpuProcessStats]:
    stats: dict[int, GpuProcessStats] = {}

    pmon = _run_nvidia_smi("pmon", "-c", "1", "-s", "u")
    for line in pmon.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[1])
            sm = float(parts[3])
        except ValueError:
            continue
        _merge_stat(stats, pid, gpu_percent=stats.get(pid, GpuProcessStats(0.0, 0)).gpu_percent + sm)

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
        current = stats.get(pid, GpuProcessStats(0.0, 0)).gpu_mem_bytes
        _merge_stat(stats, pid, gpu_mem_bytes=current + int(mem_mib * 1024 * 1024))

    return stats


def sample_gpu_by_pid() -> dict[int, GpuProcessStats]:
    """Return per-PID GPU utilization and VRAM."""
    if _try_init_nvml():
        stats = _sample_via_nvml()
        if stats:
            return stats
    if _nvidia_smi_path() is not None:
        return _sample_via_nvidia_smi()
    return {}
