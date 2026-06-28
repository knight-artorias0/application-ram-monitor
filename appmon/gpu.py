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


def _parse_float(value: str) -> float:
    value = value.strip()
    if value in {"", "-", "[N/A]", "N/A"}:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


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
        gpu_percent=max(
            current.gpu_percent,
            gpu_percent if gpu_percent is not None else current.gpu_percent,
        ),
        gpu_mem_bytes=max(
            current.gpu_mem_bytes,
            gpu_mem_bytes if gpu_mem_bytes is not None else current.gpu_mem_bytes,
        ),
    )


def _merge_stats(target: dict[int, GpuProcessStats], source: dict[int, GpuProcessStats]) -> None:
    for pid, sample in source.items():
        _merge_stat(
            target,
            pid,
            gpu_percent=sample.gpu_percent,
            gpu_mem_bytes=sample.gpu_mem_bytes,
        )


def _sample_via_nvml() -> dict[int, GpuProcessStats]:
    import pynvml  # type: ignore[import-untyped]

    stats: dict[int, GpuProcessStats] = {}
    device_count = pynvml.nvmlDeviceGetCount()
    for index in range(device_count):
        handle = pynvml.nvmlDeviceGetHandleByIndex(index)

        process_lists = []
        for getter_name in (
            "nvmlDeviceGetComputeRunningProcesses_v3",
            "nvmlDeviceGetGraphicsRunningProcesses_v3",
            "nvmlDeviceGetComputeRunningProcesses",
            "nvmlDeviceGetGraphicsRunningProcesses",
        ):
            getter = getattr(pynvml, getter_name, None)
            if getter is None:
                continue
            try:
                process_lists.append(getter(handle))
            except pynvml.NVMLError:
                continue

        for processes in process_lists:
            for process in processes:
                mem = getattr(process, "usedGpuMemory", None)
                if mem in (None, pynvml.NVML_VALUE_NOT_AVAILABLE):
                    continue
                _merge_stat(stats, int(process.pid), gpu_mem_bytes=int(mem))

        for util_getter_name in (
            "nvmlDeviceGetProcessUtilization",
            "nvmlDeviceGetProcessUtilization_v2",
        ):
            getter = getattr(pynvml, util_getter_name, None)
            if getter is None:
                continue
            try:
                samples = getter(handle, 0)
            except (pynvml.NVMLError, AttributeError, TypeError):
                continue
            for sample in samples:
                sm = float(getattr(sample, "smUtil", 0) or 0)
                _merge_stat(stats, int(sample.pid), gpu_percent=sm)

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
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _parse_smi_memory(value: str) -> int:
    value = value.strip()
    if not value or value in {"[N/A]", "N/A"}:
        return 0
    try:
        return int(float(value) * 1024 * 1024)
    except ValueError:
        return 0


def _sample_via_nvidia_smi() -> dict[int, GpuProcessStats]:
    stats: dict[int, GpuProcessStats] = {}

    pmon = _run_nvidia_smi("pmon", "-c", "1", "-s", "um")
    for line in pmon.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        sm = _parse_float(parts[3])
        mem_util = _parse_float(parts[4]) if len(parts) > 4 else 0.0
        util = sm if sm > 0 else mem_util
        if util > 0:
            _merge_stat(stats, pid, gpu_percent=util)

    for query in (
        ("--query-apps=pid,used_gpu_memory",),
        ("--query-compute-apps=pid,used_gpu_memory",),
        ("--query-graphics-apps=pid,used_gpu_memory",),
    ):
        output = _run_nvidia_smi(*query, "--format=csv,noheader,nounits")
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            mem = _parse_smi_memory(parts[1])
            if mem:
                _merge_stat(stats, pid, gpu_mem_bytes=mem)

    return stats


def sample_total_gpu_util() -> float:
    output = _run_nvidia_smi(
        "--query-gpu=utilization.gpu",
        "--format=csv,noheader,nounits",
    )
    total = 0.0
    for line in output.splitlines():
        value = _parse_float(line)
        if value > 0:
            total += value
    if total > 0:
        return total

    if _try_init_nvml():
        import pynvml  # type: ignore[import-untyped]

        try:
            for index in range(pynvml.nvmlDeviceGetCount()):
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                total += float(util.gpu)
        except Exception:
            return 0.0
    return total


def estimate_gpu_percentages(stats: dict[int, GpuProcessStats]) -> dict[int, GpuProcessStats]:
    """Fill missing per-process GPU % using total GPU util and VRAM share."""
    if not stats:
        return stats

    total_util = sample_total_gpu_util()
    if total_util <= 0:
        return stats

    total_vram = sum(item.gpu_mem_bytes for item in stats.values())
    if total_vram <= 0:
        return stats

    estimated: dict[int, GpuProcessStats] = {}
    for pid, item in stats.items():
        gpu_percent = item.gpu_percent
        if gpu_percent <= 0 and item.gpu_mem_bytes > 0:
            gpu_percent = total_util * (item.gpu_mem_bytes / total_vram)
        estimated[pid] = GpuProcessStats(
            gpu_percent=gpu_percent,
            gpu_mem_bytes=item.gpu_mem_bytes,
        )
    return estimated


def sample_gpu_by_pid() -> dict[int, GpuProcessStats]:
    """Return per-PID GPU utilization and VRAM from all available backends."""
    stats: dict[int, GpuProcessStats] = {}
    if _try_init_nvml():
        _merge_stats(stats, _sample_via_nvml())
    if _nvidia_smi_path() is not None:
        _merge_stats(stats, _sample_via_nvidia_smi())
    return estimate_gpu_percentages(stats)
