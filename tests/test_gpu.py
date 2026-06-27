"""Tests for GPU helper parsing."""

from appmon.gpu import nvidia_available, sample_gpu_by_pid


def test_sample_gpu_returns_mapping():
    result = sample_gpu_by_pid()
    assert isinstance(result, dict)


def test_nvidia_available_is_bool():
    assert isinstance(nvidia_available(), bool)
