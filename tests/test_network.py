"""Tests for network helpers."""

from appmon.network import read_socket_bytes_by_pid, read_system_network_totals


def test_read_system_network_totals_non_negative():
    rx, tx = read_system_network_totals()
    assert rx >= 0
    assert tx >= 0


def test_read_socket_bytes_by_pid_returns_mapping():
    stats = read_socket_bytes_by_pid()
    assert isinstance(stats, dict)
