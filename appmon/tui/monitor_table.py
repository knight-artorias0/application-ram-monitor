"""Custom application table widget without DataTable cursor bugs."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from appmon.metrics import AppGroup
from appmon.tui.formatting import format_bytes, format_gpu, format_network, format_network_speed, format_percent


class MonitorTable(Static, can_focus=True):
    """Render the full application list in one shot to avoid DataTable flicker."""

    DEFAULT_CSS = """
    MonitorTable {
        height: 1fr;
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("up", "select_prev", "Up", show=False),
        Binding("down", "select_next", "Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("home", "select_first", "Home", show=False),
        Binding("end", "select_last", "End", show=False),
    ]

    class SelectionChanged(Message):
        def __init__(self, table: MonitorTable, group_key: str | None) -> None:
            super().__init__()
            self.table = table
            self.group_key = group_key

    def __init__(self, **kwargs) -> None:
        super().__init__("", markup=False, **kwargs)
        self._rows: list[AppGroup] = []
        self._selected_key: str | None = None
        self._scroll_top = 0
        self._gpu_available = False
        self._network_estimated = False
        self._visible_rows = 18
        self._last_signature: tuple[tuple, ...] = ()

    @property
    def selected_key(self) -> str | None:
        return self._selected_key

    def set_rows(
        self,
        rows: list[AppGroup],
        *,
        gpu_available: bool,
        network_estimated: bool,
    ) -> None:
        self._rows = rows
        self._gpu_available = gpu_available
        self._network_estimated = network_estimated

        keys = {row.key for row in rows}
        if self._selected_key not in keys:
            self._selected_key = rows[0].key if rows else None
            self._scroll_top = 0

        self._clamp_scroll()
        signature = self._signature()
        if signature != self._last_signature:
            self._last_signature = signature
            self._paint()

    def _signature(self) -> tuple[tuple, ...]:
        return tuple(
            (
                row.key,
                row.pss_bytes,
                round(row.cpu_percent, 1),
                round(row.gpu_percent, 1),
                row.gpu_mem_bytes,
                round(row.net_down_bps, -2),
                round(row.net_up_bps, -2),
                row.socket_count,
                row.process_count,
            )
            for row in self._rows
        )

    def _selected_index(self) -> int:
        for index, row in enumerate(self._rows):
            if row.key == self._selected_key:
                return index
        return 0

    def _clamp_scroll(self) -> None:
        if not self._rows:
            self._scroll_top = 0
            return
        selected = self._selected_index()
        if selected < self._scroll_top:
            self._scroll_top = selected
        bottom = self._scroll_top + self._visible_rows
        if selected >= bottom:
            self._scroll_top = max(0, selected - self._visible_rows + 1)

    def _paint(self) -> None:
        if not self._rows:
            self.update("No applications found.")
            return

        table = Table(
            expand=True,
            box=None,
            pad_edge=False,
            padding=(0, 1),
            show_header=True,
            header_style="bold",
        )
        table.add_column("Application", ratio=3, no_wrap=True)
        table.add_column("RAM", justify="right", no_wrap=True)
        table.add_column("CPU%", justify="right", no_wrap=True)
        table.add_column("GPU%", justify="right", no_wrap=True)
        table.add_column("Net", ratio=2, no_wrap=True)
        table.add_column("Procs", justify="right", no_wrap=True)

        end = min(self._scroll_top + self._visible_rows, len(self._rows))
        for index in range(self._scroll_top, end):
            row = self._rows[index]
            selected = row.key == self._selected_key
            marker = "▸ " if selected else "  "
            app_name = Text(f"{marker}{row.display_name}")
            if selected:
                app_name.stylize("reverse bold")
            gpu = format_gpu(row, self._gpu_available)
            cells = [
                app_name,
                format_bytes(row.pss_bytes),
                format_percent(row.cpu_percent),
                gpu,
                format_network(row, estimated=self._network_estimated),
                str(row.process_count),
            ]
            if selected:
                table.add_row(*cells, style="reverse")
            else:
                table.add_row(*cells)

        self.update(table)

    def _notify_selection(self) -> None:
        self.post_message(self.SelectionChanged(self, self._selected_key))

    def action_select_prev(self) -> None:
        if not self._rows:
            return
        index = max(self._selected_index() - 1, 0)
        self._selected_key = self._rows[index].key
        self._clamp_scroll()
        self._paint()
        self._notify_selection()

    def action_select_next(self) -> None:
        if not self._rows:
            return
        index = min(self._selected_index() + 1, len(self._rows) - 1)
        self._selected_key = self._rows[index].key
        self._clamp_scroll()
        self._paint()
        self._notify_selection()

    def action_page_up(self) -> None:
        if not self._rows:
            return
        self._scroll_top = max(0, self._scroll_top - self._visible_rows)
        self._paint()

    def action_page_down(self) -> None:
        if not self._rows:
            return
        max_top = max(0, len(self._rows) - self._visible_rows)
        self._scroll_top = min(max_top, self._scroll_top + self._visible_rows)
        self._paint()

    def action_select_first(self) -> None:
        if not self._rows:
            return
        self._selected_key = self._rows[0].key
        self._scroll_top = 0
        self._paint()
        self._notify_selection()

    def action_select_last(self) -> None:
        if not self._rows:
            return
        self._selected_key = self._rows[-1].key
        self._scroll_top = max(0, len(self._rows) - self._visible_rows)
        self._paint()
        self._notify_selection()

    def on_resize(self) -> None:
        self._visible_rows = max(6, self.size.height - 2)
        self._clamp_scroll()
        if self._rows:
            self._paint()
