"""Textual terminal UI for application-level monitoring."""

from __future__ import annotations

from enum import Enum

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable, Footer, Header, Input, Static

from appmon.metrics import AppGroup, MetricsCollector, SystemSnapshot

COLUMN_SPECS = (
    ("Application", "application"),
    ("RAM", "ram"),
    ("CPU%", "cpu"),
    ("GPU%", "gpu"),
    ("Net", "net"),
    ("Procs", "procs"),
)


def format_bytes(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "0 B"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(num_bytes)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def format_percent(value: float) -> str:
    return f"{value:5.1f}%"


def format_bitrate(bps: float) -> str:
    if bps <= 0:
        return "0 bps"
    units = ("bps", "Kbps", "Mbps", "Gbps")
    value = float(bps)
    unit = units[0]
    for unit in units:
        if value < 1000 or unit == units[-1]:
            break
        value /= 1000
    if unit == "bps":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def format_network(group: AppGroup, accounting: bool) -> str:
    if accounting:
        return f"↓{format_bitrate(group.net_down_bps)} ↑{format_bitrate(group.net_up_bps)}"
    if group.socket_count > 0:
        return f"{group.socket_count} sock"
    return "-"


class SortKey(str, Enum):
    RAM = "ram"
    CPU = "cpu"
    GPU = "gpu"
    NET = "net"
    NAME = "name"
    PROCS = "procs"


class SummaryBar(Static):
    def update_snapshot(self, snapshot: SystemSnapshot) -> None:
        total = format_bytes(snapshot.total_mem_bytes)
        used = format_bytes(snapshot.used_mem_bytes)
        cpu = format_percent(snapshot.total_cpu_percent)
        parts = [f"Memory: {used} / {total}", f"CPU: {cpu}"]
        if snapshot.gpu_available:
            parts.append(f"GPU: {format_percent(snapshot.total_gpu_percent)}")
        if snapshot.network_accounting:
            parts.append(
                f"Net: ↓{format_bitrate(snapshot.total_net_down_bps)} "
                f"↑{format_bitrate(snapshot.total_net_up_bps)}"
            )
        else:
            parts.append(
                f"Net: ↓{format_bitrate(snapshot.total_net_down_bps)} "
                f"↑{format_bitrate(snapshot.total_net_up_bps)} (system)"
            )
        if snapshot.pss_fallback:
            parts.append("(RSS fallback)")
        text = "   ".join(parts)
        if self.renderable != text:
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

    DataTable {
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
        self.selected_group: AppGroup | None = None
        self._focused_row_key: str | None = None
        self._display_order: list[str] = []
        self._groups_by_key: dict[str, AppGroup] = {}
        self._refreshing_table = False
        self._network_accounting = False
        self._gpu_available = False
        self._last_detail_text = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Filter applications...", id="search")
        yield SummaryBar("Collecting metrics...", id="summary")
        with Container(id="main"):
            yield DataTable(id="apps", zebra_stripes=False, cursor_type="row")
            yield Static("Select an application with arrow keys to inspect processes.", id="detail")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#apps", DataTable)
        table.add_columns(*COLUMN_SPECS)
        self.set_interval(self.interval, self.refresh_metrics)
        snapshot = self.collector.sample()
        self.query_one("#summary", SummaryBar).update_snapshot(snapshot)
        self._render_table(snapshot, reorder=True)

    def _group_sort_value(self, group: AppGroup) -> float | str | int:
        if self.sort_key == SortKey.CPU:
            return group.cpu_percent
        if self.sort_key == SortKey.GPU:
            return group.gpu_percent
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

    def _live_focused_key(self, table: DataTable) -> str | None:
        if table.row_count == 0:
            return self._focused_row_key
        try:
            coordinate = table.cursor_coordinate
            if table.is_valid_coordinate(coordinate):
                cell_key = table.coordinate_to_cell_key(coordinate)
                return str(cell_key.row_key.value)
        except Exception:
            return self._focused_row_key
        return self._focused_row_key

    def _ordered_row_keys(self, table: DataTable) -> list[str]:
        return [str(row.key.value) for row in table.ordered_rows]

    def _gpu_cell(self, group: AppGroup) -> str:
        if not self._gpu_available:
            return "-"
        if group.gpu_mem_bytes > 0 and group.gpu_percent <= 0:
            return f"{format_bytes(group.gpu_mem_bytes)}"
        return format_percent(group.gpu_percent)

    def _row_values(self, group: AppGroup) -> dict[str, str]:
        return {
            "application": group.display_name,
            "ram": format_bytes(group.pss_bytes),
            "cpu": format_percent(group.cpu_percent),
            "gpu": self._gpu_cell(group),
            "net": format_network(group, self._network_accounting),
            "procs": str(group.process_count),
        }

    def _cell_changed(self, table: DataTable, row_key: str, column_key: str, value: str) -> bool:
        try:
            current = table.get_cell(row_key, column_key)
        except Exception:
            return True
        return str(current) != value

    def _update_group_row(self, table: DataTable, group: AppGroup) -> bool:
        changed = False
        for column_key, value in self._row_values(group).items():
            if self._cell_changed(table, group.key, column_key, value):
                table.update_cell(group.key, column_key, value)
                changed = True
        return changed

    def _restore_viewport(self, table: DataTable, scroll_y: int, scroll_x: int, focused_key: str | None) -> None:
        table.scroll_x = scroll_x
        table.scroll_y = scroll_y
        if focused_key and focused_key in self._groups_by_key:
            try:
                table.move_cursor(row=table.get_row_index(focused_key), scroll=False)
            except Exception:
                pass
        table.scroll_x = scroll_x
        table.scroll_y = scroll_y

    def _set_detail_message(self, text: str) -> None:
        if text == self._last_detail_text:
            return
        self._last_detail_text = text
        self.query_one("#detail", Static).update(text)

    def _rebuild_table(self, table: DataTable, visible: list[AppGroup], focused_key: str | None) -> None:
        scroll_y = table.scroll_y
        scroll_x = table.scroll_x
        self._refreshing_table = True
        with self.batch_update():
            table.clear(columns=False)
            for group in visible:
                values = self._row_values(group)
                table.add_row(
                    values["application"],
                    values["ram"],
                    values["cpu"],
                    values["gpu"],
                    values["net"],
                    values["procs"],
                    key=group.key,
                )

        def finish_rebuild() -> None:
            try:
                self._restore_viewport(table, scroll_y, scroll_x, focused_key)
            finally:
                self._refreshing_table = False
            if focused_key and focused_key in self._groups_by_key:
                self._show_detail(self._groups_by_key[focused_key])
            elif not visible:
                self._set_detail_message("No matching applications.")
            elif focused_key is None:
                self._set_detail_message("Select an application with arrow keys to inspect processes.")
            else:
                self._set_detail_message("Selected application is no longer visible.")

        self.call_after_refresh(finish_rebuild)

    def _render_table(self, snapshot: SystemSnapshot, *, reorder: bool = False) -> None:
        table = self.query_one("#apps", DataTable)
        focused_key = self._live_focused_key(table)
        if focused_key is not None:
            self._focused_row_key = focused_key

        scroll_y = table.scroll_y
        scroll_x = table.scroll_x

        self._groups_by_key = {group.key: group for group in snapshot.groups}
        self._network_accounting = snapshot.network_accounting
        self._gpu_available = snapshot.gpu_available

        filtered = self._filtered_groups(snapshot.groups)
        visible = self._sync_display_order(filtered, reorder=reorder)
        desired_keys = [group.key for group in visible]
        current_keys = self._ordered_row_keys(table)

        if desired_keys == current_keys and desired_keys:
            changed = False
            with self.batch_update():
                for group in visible:
                    if self._update_group_row(table, group):
                        changed = True
            if changed:
                self.call_after_refresh(
                    lambda: self._restore_viewport(table, scroll_y, scroll_x, focused_key)
                )
            if focused_key and focused_key in self._groups_by_key:
                self._show_detail(self._groups_by_key[focused_key])
            return

        self._rebuild_table(table, visible, focused_key)

    def _detail_text(self, group: AppGroup) -> str:
        lines = [
            (
                f"{group.display_name} ({group.key}) — {group.process_count} process(es), "
                f"source: {group.source}"
            ),
            "PID      RAM        CPU%     GPU%     Net                  COMM",
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
                self._network_accounting,
            )
            gpu = format_percent(proc.gpu_percent) if self._gpu_available else "-"
            lines.append(
                f"{proc.pid:<8} {format_bytes(proc.pss_bytes):>10} "
                f"{format_percent(proc.cpu_percent):>8} {gpu:>8} {net:<20} {proc.comm}"
            )
        if len(group.processes) > 12:
            lines.append(f"... and {len(group.processes) - 12} more")
        return "\n".join(lines)

    def _show_detail(self, group: AppGroup) -> None:
        self.selected_group = group
        self._set_detail_message(self._detail_text(group))

    def refresh_metrics(self) -> None:
        snapshot = self.collector.sample()
        self.query_one("#summary", SummaryBar).update_snapshot(snapshot)
        self._render_table(snapshot, reorder=False)

    def action_search(self) -> None:
        search = self.query_one("#search", Input)
        search.add_class("visible")
        search.focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        search.value = ""
        search.remove_class("visible")
        self.filter_text = ""
        snapshot = self.collector.sample()
        self._render_table(snapshot, reorder=True)
        self.query_one("#apps", DataTable).focus()

    def action_cycle_sort(self) -> None:
        order = [SortKey.RAM, SortKey.CPU, SortKey.GPU, SortKey.NET, SortKey.NAME, SortKey.PROCS]
        idx = order.index(self.sort_key)
        self.sort_key = order[(idx + 1) % len(order)]
        self.sort_reverse = self.sort_key != SortKey.NAME
        self.notify(f"Sorted by {self.sort_key.value}")
        snapshot = self.collector.sample()
        self._render_table(snapshot, reorder=True)

    @on(Input.Submitted, "#search")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        self.filter_text = event.value.strip()
        event.input.remove_class("visible")
        self.query_one("#apps", DataTable).focus()
        snapshot = self.collector.sample()
        self._render_table(snapshot, reorder=True)

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._refreshing_table or event.row_key is None:
            return
        row_key = str(event.row_key.value)
        if row_key == self._focused_row_key:
            return
        self._focused_row_key = row_key
        group = self._groups_by_key.get(row_key)
        if group is not None:
            self._show_detail(group)

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None:
            return
        self._focused_row_key = str(event.row_key.value)
        group = self._groups_by_key.get(self._focused_row_key)
        if group is not None:
            self._show_detail(group)


def run_tui(interval: float = 1.0) -> None:
    AppMonitorApp(interval=interval).run()
