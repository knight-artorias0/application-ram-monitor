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
    ("Procs", "procs"),
    ("Source", "source"),
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


class SortKey(str, Enum):
    RAM = "ram"
    CPU = "cpu"
    NAME = "name"
    PROCS = "procs"


class SummaryBar(Static):
    def update_snapshot(self, snapshot: SystemSnapshot) -> None:
        total = format_bytes(snapshot.total_mem_bytes)
        used = format_bytes(snapshot.used_mem_bytes)
        cpu = format_percent(snapshot.total_cpu_percent)
        fallback = " (RSS fallback)" if snapshot.pss_fallback else ""
        self.update(f"Memory: {used} / {total}   CPU: {cpu}{fallback}")


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
        height: 8;
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
        self._groups_by_key: dict[str, AppGroup] = {}
        self._refreshing_table = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Input(placeholder="Filter applications...", id="search")
        yield SummaryBar("Collecting metrics...", id="summary")
        with Container(id="main"):
            yield DataTable(id="apps", zebra_stripes=True, cursor_type="row")
            yield Static("Select an application and press Enter to inspect processes.", id="detail")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#apps", DataTable)
        table.add_columns(*COLUMN_SPECS)
        self.set_interval(self.interval, self.refresh_metrics)
        self.refresh_metrics()

    def _sorted_groups(self, groups: list[AppGroup]) -> list[AppGroup]:
        def key_fn(group: AppGroup) -> float | str | int:
            if self.sort_key == SortKey.CPU:
                return group.cpu_percent
            if self.sort_key == SortKey.NAME:
                return group.display_name.lower()
            if self.sort_key == SortKey.PROCS:
                return group.process_count
            return group.pss_bytes

        return sorted(groups, key=key_fn, reverse=self.sort_reverse)

    def _filtered_groups(self, groups: list[AppGroup]) -> list[AppGroup]:
        if not self.filter_text:
            return groups
        needle = self.filter_text.casefold()
        return [
            group
            for group in groups
            if needle in group.display_name.casefold() or needle in group.key.casefold()
        ]

    def _capture_focused_key(self, table: DataTable) -> str | None:
        if self._focused_row_key:
            return self._focused_row_key
        if table.row_count == 0:
            return None
        try:
            coordinate = table.cursor_coordinate
            if table.is_valid_coordinate(coordinate):
                cell_key = table.coordinate_to_cell_key(coordinate)
                return str(cell_key.row_key.value)
        except Exception:
            return None
        return None

    def _ordered_row_keys(self, table: DataTable) -> list[str]:
        return [str(row.key.value) for row in table.ordered_rows]

    def _update_group_row(self, table: DataTable, group: AppGroup) -> None:
        table.update_cell(group.key, "application", group.display_name)
        table.update_cell(group.key, "ram", format_bytes(group.pss_bytes))
        table.update_cell(group.key, "cpu", format_percent(group.cpu_percent))
        table.update_cell(group.key, "procs", str(group.process_count))
        table.update_cell(group.key, "source", group.source)

    def _update_detail_panel(self, focused_key: str | None, visible: list[AppGroup]) -> None:
        detail = self.query_one("#detail", Static)
        if focused_key and focused_key in self._groups_by_key:
            self._show_detail(self._groups_by_key[focused_key])
        elif not visible:
            detail.update("No matching applications.")
        elif focused_key is None:
            detail.update("Select an application with arrow keys to inspect processes.")
        else:
            detail.update("Selected application is no longer visible.")

    def _rebuild_table(self, table: DataTable, visible: list[AppGroup], focused_key: str | None) -> None:
        self._refreshing_table = True
        table.clear(columns=False)
        for group in visible:
            table.add_row(
                group.display_name,
                format_bytes(group.pss_bytes),
                format_percent(group.cpu_percent),
                str(group.process_count),
                group.source,
                key=group.key,
            )

        def finish_rebuild() -> None:
            try:
                if focused_key and focused_key in self._groups_by_key:
                    table.move_cursor(row=table.get_row_index(focused_key), scroll=False)
            finally:
                self._refreshing_table = False
            self._update_detail_panel(focused_key, visible)

        self.call_after_refresh(finish_rebuild)

    def _render_table(self, snapshot: SystemSnapshot) -> None:
        table = self.query_one("#apps", DataTable)
        focused_key = self._capture_focused_key(table)
        if focused_key is not None:
            self._focused_row_key = focused_key

        self._groups_by_key = {group.key: group for group in snapshot.groups}
        visible = self._sorted_groups(self._filtered_groups(snapshot.groups))
        desired_keys = [group.key for group in visible]
        current_keys = self._ordered_row_keys(table)

        if desired_keys == current_keys and desired_keys:
            for group in visible:
                self._update_group_row(table, group)
            self._update_detail_panel(focused_key, visible)
            return

        self._rebuild_table(table, visible, focused_key)

    def _show_detail(self, group: AppGroup) -> None:
        self.selected_group = group
        lines = [
            f"{group.display_name} ({group.key}) — {group.process_count} process(es), source: {group.source}",
            "PID      RAM        CPU%     COMM",
        ]
        for proc in sorted(group.processes, key=lambda p: p.pss_bytes, reverse=True)[:12]:
            lines.append(
                f"{proc.pid:<8} {format_bytes(proc.pss_bytes):>10} {format_percent(proc.cpu_percent):>8}  {proc.comm}"
            )
        if len(group.processes) > 12:
            lines.append(f"... and {len(group.processes) - 12} more")
        self.query_one("#detail", Static).update("\n".join(lines))

    def refresh_metrics(self) -> None:
        snapshot = self.collector.sample()
        self.query_one("#summary", SummaryBar).update_snapshot(snapshot)
        self._render_table(snapshot)

    def action_search(self) -> None:
        search = self.query_one("#search", Input)
        search.add_class("visible")
        search.focus()

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        search.value = ""
        search.remove_class("visible")
        self.filter_text = ""
        self.refresh_metrics()
        self.query_one("#apps", DataTable).focus()

    def action_cycle_sort(self) -> None:
        order = [SortKey.RAM, SortKey.CPU, SortKey.NAME, SortKey.PROCS]
        idx = order.index(self.sort_key)
        self.sort_key = order[(idx + 1) % len(order)]
        if self.sort_key in (SortKey.RAM, SortKey.CPU, SortKey.PROCS):
            self.sort_reverse = True
        else:
            self.sort_reverse = False
        self.notify(f"Sorted by {self.sort_key.value}")
        snapshot = self.collector.sample()
        self._render_table(snapshot)

    @on(Input.Submitted, "#search")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        self.filter_text = event.value.strip()
        event.input.remove_class("visible")
        self.query_one("#apps", DataTable).focus()
        self.refresh_metrics()

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._refreshing_table or event.row_key is None:
            return
        self._focused_row_key = str(event.row_key.value)
        group = self._groups_by_key.get(self._focused_row_key)
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
