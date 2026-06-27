"""Tests for network helpers."""

from appmon.network import read_socket_count, read_system_network_totals


def test_read_system_network_totals_non_negative():
    rx, tx = read_system_network_totals()
    assert rx >= 0
    assert tx >= 0


def test_read_socket_count_for_self():
    import os

    count = read_socket_count(os.getpid())
    assert count >= 0
