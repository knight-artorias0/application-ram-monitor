"""Tests for process grouping heuristics."""

from appmon.cgroup import GroupSource
from appmon.grouping import GroupKey, resolve_group
from appmon.proc import ProcessInfo


def _proc(
    pid: int,
    *,
    comm: str = "proc",
    exe: str | None = "/usr/bin/proc",
    cmdline: str = "",
    cgroup_path: str = "",
    ppid: int = 1,
) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        comm=comm,
        exe=exe,
        cmdline=cmdline,
        cgroup_path=cgroup_path,
        pss_bytes=1024,
        rss_bytes=1024,
        utime=0,
        stime=0,
        ppid=ppid,
    )


def test_groups_by_cgroup_app_id():
    process = _proc(
        100,
        cgroup_path="/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.mozilla.firefox-1.scope",
    )
    group = resolve_group(process, {})
    assert group.key == "org.mozilla.firefox"
    assert group.source == GroupSource.CGROUP


def test_groups_by_exe_when_no_cgroup():
    process = _proc(200, exe="/usr/bin/python3", comm="python3")
    group = resolve_group(process, {})
    assert group.key == "python3"
    assert group.source == GroupSource.EXE


def test_browser_content_process_uses_parent_exe():
    parent = _proc(300, exe="/usr/lib/firefox/firefox", comm="firefox")
    child = _proc(301, comm="Web Content", exe=None, ppid=300)
    parent_index = {300: parent.exe or ""}
    group = resolve_group(child, parent_index)
    assert group.key == "firefox"
    assert group.source == GroupSource.EXE


def test_code_oss_alias():
    process = _proc(400, exe="/usr/share/code/code-oss", comm="code-oss")
    group = resolve_group(process, {})
    assert group.key == "code"
