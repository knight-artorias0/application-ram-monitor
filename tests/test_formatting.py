"""Tests for display formatting."""

from appmon.metrics import AppGroup
from appmon.tui.formatting import format_network_speed


def test_network_speed_mbps():
    assert format_network_speed(12_500_000) == "12.5 Mbps"


def test_network_speed_gbps():
    assert format_network_speed(2_500_000_000) == "2.50 Gbps"


def test_network_speed_zero():
    assert format_network_speed(0) == "0 Mbps"
