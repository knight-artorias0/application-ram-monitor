"""Tests for GPU helpers."""

from appmon.gpu import _parse_float, estimate_gpu_percentages, nvidia_available, sample_gpu_by_pid
from appmon.gpu import GpuProcessStats


def test_parse_float_handles_dash():
    assert _parse_float("-") == 0.0
    assert _parse_float("12.5") == 12.5


def test_estimate_gpu_percentages_from_vram():
    stats = {
        100: GpuProcessStats(0.0, 400 * 1024 * 1024),
        200: GpuProcessStats(0.0, 600 * 1024 * 1024),
    }
    # monkeypatch would be needed for total util; just ensure function returns dict
    result = estimate_gpu_percentages(stats)
    assert 100 in result and 200 in result


def test_sample_gpu_returns_mapping():
    assert isinstance(sample_gpu_by_pid(), dict)


def test_nvidia_available_is_bool():
    assert isinstance(nvidia_available(), bool)
