"""Tests for cgroup path parsing."""

from appmon.cgroup import GroupSource, parse_cgroup_path


def test_kde_app_scope():
    path = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.kde.dolphin-81510.scope"
    match = parse_cgroup_path(path)
    assert match is not None
    assert match.app_id == "org.kde.dolphin"
    assert match.source == GroupSource.CGROUP


def test_firefox_app_scope():
    path = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.mozilla.firefox-12345.scope"
    match = parse_cgroup_path(path)
    assert match is not None
    assert match.app_id == "org.mozilla.firefox"
    assert match.source == GroupSource.CGROUP


def test_flatpak_scope():
    path = "/user.slice/user-1000.slice/user@1000.service/app.slice/app-flatpak-com.discordapp.Discord-abcdef12-3456-7890-abcd-ef1234567890.scope"
    match = parse_cgroup_path(path)
    assert match is not None
    assert match.app_id == "com.discordapp.Discord"
    assert match.source == GroupSource.FLATPAK


def test_dbus_scope():
    path = "/user.slice/user-1000.slice/user@1000.service/app.slice/dbus-org.gnome.Nautilus-99999.scope"
    match = parse_cgroup_path(path)
    assert match is not None
    assert match.app_id == "org.gnome.Nautilus"
    assert match.source == GroupSource.CGROUP


def test_snap_scope():
    path = "/user.slice/user-1000.slice/user@1000.service/app.slice/snap.1234abcd.firefox.firefox.scope"
    match = parse_cgroup_path(path)
    assert match is not None
    assert match.app_id == "firefox.firefox"
    assert match.source == GroupSource.SNAP


def test_empty_path():
    assert parse_cgroup_path("") is None
