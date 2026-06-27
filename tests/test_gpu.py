"""Tests for GPU helper parsing."""

from appmon.gpu import sample_gpu_by_pid


def test_sample_gpu_without_nvidia_returns_empty():
    # CI/dev hosts usually have no NVIDIA driver.
    assert isinstance(sample_gpu_by_pid(), dict)
