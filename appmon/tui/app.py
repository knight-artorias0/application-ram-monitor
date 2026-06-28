"""Textual terminal UI for application-level monitoring."""

from __future__ import annotations

from enum import Enum

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Input, Static

from appmon.metrics import AppGroup, MetricsCollector, SystemSnapshot
from appmon.tui.formatting import format_bytes, format_network, format_network_speed, format_percent
from appmon.tui.monitor_table import MonitorTable


class SortKey(str, Enum):
    RAM = "ram"
    CPU = "cpu"
    NET = "net"
    NAME = "name"
    PROCS = "procs"


class SummaryBar(Static):
    def update_snapshot(self, snapshot: SystemSnapshot) -> None:
        total = format_bytes(snapshot.total_mem_bytes)
        used = format_bytes(snapshot.used_mem_bytes)
        cpu = format_percent(snapshot.total_cpu_percent)
        net_suffix = "~" if snapshot.network_estimated else ""
        parts = [
            f"Memory: {used} / {total}",
            f"CPU: {cpu}",
            (
                f"Net: ↓{format_network_speed(snapshot.total_net_down_bps)}{net_suffix} "
                f"↑{format_network_speed(snapshot.total_net_up_bps)}{net_suffix}"
            ),
        ]
        if snapshot.pss_fallback:
            parts.append("(RSS fallback)")
        text = "   ".join(parts)
        if self.content != text:
            self.update(text)


class AppMonitorApp(App):
    CSS = """
    Screen {
        background: $surface;
    }

    #main {
        height: 1fr;
    }

    #summary {
        height: 3;
        padding: 0 1;
        background: $panel;
        color: $text;
    }

    #search {
        dock: top;
        display: none;
    }

    #search.visible {
        display: block;
    }

    MonitorTable {
        height: 1fr;
    }

    #detail {
        height: 9;
        padding: 0 1;
        background: $panel;
        border-top: solid $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("slash", "search", "Search", show=False),
        Binding("s", "cycle_sort", "Sort"),
        Binding("escape", "clear_search", "Clear search", show=False),
    ]

    def __init__(self, interval: float = 1.0) -> None:
        super().__init__()
        self.interval = interval
        self.collector = MetricsCollector()
        self.sort_key = SortKey.RAM
        self.sort_reverse = True
        self.filter_text = ""
        self._display_order: list[str] = []
        self._groups_by_key: dict[str, AppGroup] = {}
        self._network_estimated = False
        self._last_detail_text = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Filter applications...", id="search")
        yield SummaryBar("Collecting metrics...", id="summary")
        with Container(id="main"):
            yield MonitorTable(id="apps")
            yield Static("↑/↓ select app   PgUp/PgDn scroll list   s sort   / filter   q quit", id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(self.interval, self.refresh_metrics)
        self.refresh_metrics(reorder=True)

    def _group_sort_value(self, group: AppGroup) -> float | str | int:
        if self.sort_key == SortKey.CPU:
            return group.cpu_percent
        if self.sort_key == SortKey.NET:
            return group.net_down_bps + group.net_up_bps
        if self.sort_key == SortKey.NAME:
            return group.display_name.lower()
        if self.sort_key == SortKey.PROCS:
            return group.process_count
        return group.pss_bytes

    def _sorted_groups(self, groups: list[AppGroup]) -> list[AppGroup]:
        return sorted(
            groups,
            key=lambda group: (self._group_sort_value(group), group.display_name.lower()),
            reverse=self.sort_reverse,
        )

    def _filtered_groups(self, groups: list[AppGroup]) -> list[AppGroup]:
        if not self.filter_text:
            return groups
        needle = self.filter_text.casefold()
        return [
            group
            for group in groups
            if needle in group.display_name.casefold() or needle in group.key.casefold()
        ]

    def _sync_display_order(self, filtered: list[AppGroup], *, reorder: bool) -> list[AppGroup]:
        filtered_by_key = {group.key: group for group in filtered}
        if reorder or not self._display_order:
            self._display_order = [group.key for group in self._sorted_groups(filtered)]
        else:
            self._display_order = [
                key for key in self._display_order if key in filtered_by_key
            ]
            for group in filtered:
                if group.key not in self._display_order:
                    self._display_order.append(group.key)
        return [filtered_by_key[key] for key in self._display_order if key in filtered_by_key]

    def _detail_text(self, group: AppGroup) -> str:
        lines = [
            (
                f"{group.display_name} ({group.key}) — {group.process_count} process(es), "
                f"source: {group.source}"
            ),
            "PID      RAM        CPU%     Net                  COMM",
        ]
        for proc in sorted(group.processes, key=lambda p: p.pss_bytes, reverse=True)[:12]:
            net = format_network(
                AppGroup(
                    key=group.key,
                    display_name=group.display_name,
                    source=group.source,
                    net_down_bps=proc.net_down_bps,
                    net_up_bps=proc.net_up_bps,
                    socket_count=proc.socket_count,
                ),
                estimated=self._network_estimated,
            )
            lines.append(
                f"{proc.pid:<8} {format_bytes(proc.pss_bytes):>10} "
                f"{format_percent(proc.cpu_percent):>8} {net:<20} {proc.comm}"
            )
        if len(group.processes) > 12:
            lines.append(f"... and {len(group.processes) - 12} more")
        return "\n".join(lines)

    def _show_detail(self, group: AppGroup | None) -> None:
        detail = self.query_one("#detail", Static)
        if group is None:
            text = "↑/↓ select app   PgUp/PgDn scroll list   s sort   / filter   q quit"
        else:
            text = self._detail_text(group)
        if text == self._last_detail_text:
            return
        self._last_detail_text = text
        detail.update(text)

    def refresh_metrics(self, *, reorder: bool = False) -> None:
        snapshot = self.collector.sample()
        self.query_one("#summary", SummaryBar).update_snapshot(snapshot)

        self._groups_by_key = {group.key: group for group in snapshot.groups}
        self._network_estimated = snapshot.network_estimated

        visible = self._sync_display_order(self._filtered_groups(snapshot.groups), reorder=reorder)
        table = self.query_one("#apps", MonitorTable)
        with self.batch_update():
            table.set_rows(
                visible,
                network_estimated=snapshot.network_estimated,
            )
            selected = table.selected_key
            if selected and selected in self._groups_by_key:
                self._show_detail(self._groups_by_key[selected])

    def action_search(self) -> None:
        search = self.query_one("#search", Input)
        search.add_class("visible")
        search.focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        search.value = ""
        search.remove_class("visible")
        self.filter_text = ""
        self.refresh_metrics(reorder=True)
        self.query_one("#apps", MonitorTable).focus()

    def action_cycle_sort(self) -> None:
        order = [SortKey.RAM, SortKey.CPU, SortKey.NET, SortKey.NAME, SortKey.PROCS]
        idx = order.index(self.sort_key)
        self.sort_key = order[(idx + 1) % len(order)]
        self.sort_reverse = self.sort_key != SortKey.NAME
        self.notify(f"Sorted by {self.sort_key.value}")
        self.refresh_metrics(reorder=True)

    @on(Input.Submitted, "#search")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        self.filter_text = event.value.strip()
        event.input.remove_class("visible")
        self.query_one("#apps", MonitorTable).focus()
        self.refresh_metrics(reorder=True)

    @on(MonitorTable.SelectionChanged)
    def on_selection_changed(self, event: MonitorTable.SelectionChanged) -> None:
        if event.group_key and event.group_key in self._groups_by_key:
            self._show_detail(self._groups_by_key[event.group_key])


def run_tui(interval: float = 1.0) -> None:
    AppMonitorApp(interval=interval).run()
