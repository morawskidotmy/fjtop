import contextlib
import curses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ContainerInfo


def fmt_time(s: float) -> str:
    s = int(s)
    h, m = divmod(s, 3600)
    m, s = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def fmt_bytes(n: int | float) -> str:
    for u in ("B", "K", "M", "G"):
        if abs(n) < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}T"


COLUMNS = [
    ("PID", "pid", 7),
    ("USER", "user", 8),
    ("CPU%", "cpu_pct", 5),
    ("MEM%", "mem_pct", 5),
    ("RSS", "rss_bytes", 7),
    ("TIME+", "cpu_time_sec", 8),
    ("AGE", "age_sec", 8),
    ("PROCESS", "name", 0),
]

SORT_ALIASES: dict[str, str] = {
    "c": "cpu_pct",
    "m": "mem_pct",
    "p": "pid",
    "r": "rss_bytes",
    "a": "age_sec",
    "t": "cpu_time_sec",
    "n": "name",
    "u": "user",
}


def _col_widths(available: int) -> dict[str, int]:
    """Distribute available width across columns."""
    fixed = sum(w for _, _, w in COLUMNS if w > 0)
    fixed_count = sum(1 for _, _, w in COLUMNS if w > 0)
    # spaces between fixed columns and trailing space before process
    separators = fixed_count
    process_w = max(12, available - fixed - separators)
    widths = {key: w for _, key, w in COLUMNS if w > 0}
    widths["name"] = process_w
    return widths


class UI:
    def __init__(self) -> None:
        self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        self.stdscr.keypad(True)
        self.stdscr.timeout(1000)
        self.stdscr.clear()

        self.has_colors = curses.has_colors()
        if self.has_colors:
            curses.start_color()
            with contextlib.suppress(curses.error):
                curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
            curses.init_pair(3, curses.COLOR_RED, -1)
            curses.init_pair(4, curses.COLOR_CYAN, -1)
            curses.init_pair(5, curses.COLOR_WHITE, -1)
            curses.init_pair(6, curses.COLOR_BLUE, -1)

    def cleanup(self) -> None:
        curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()

    def get_key(self) -> str | None:
        try:
            ch = self.stdscr.getch()
        except curses.error:
            return None
        if ch == -1:
            return None
        if ch == curses.KEY_UP:
            return "UP"
        if ch == curses.KEY_DOWN:
            return "DOWN"
        if ch == curses.KEY_RESIZE:
            return "RESIZE"
        if ch == curses.KEY_ENTER or ch == 10 or ch == 13:
            return "ENTER"
        if ch == 27:
            return "ESC"
        if ch == 127 or ch == curses.KEY_BACKSPACE:
            return "BACKSPACE"
        if ch == curses.KEY_DC:
            return "DELETE"
        if 0 <= ch < 256:
            return chr(ch)
        return None

    def _attr(self, color: int, bold: bool = False) -> int:
        attr = curses.color_pair(color)
        if bold:
            attr |= curses.A_BOLD
        return attr

    def _cpu_attr(self, pct: float) -> int:
        if pct > 80:
            return self._attr(3)
        if pct > 40:
            return self._attr(2)
        return self._attr(1)

    def _mem_attr(self, pct: float) -> int:
        if pct > 50:
            return self._attr(3)
        if pct > 20:
            return self._attr(2)
        return self._attr(1)

    def _safe_addstr(self, row: int, col: int, text: str, attr: int = 0) -> None:
        if row < 0:
            return
        h, w = self.stdscr.getmaxyx()
        if row >= h or col >= w:
            return
        if col < 0:
            text = text[-col:]
            col = 0
        if not text:
            return
        # truncate to visible width
        avail = w - col
        if avail <= 0:
            return
        text = text[:avail]
        with contextlib.suppress(curses.error):
            self.stdscr.addstr(row, col, text, attr)

    def read_filter(self) -> str:
        h, _w = self.stdscr.getmaxyx()
        result: list[str] = []
        prompt = "Filter: "
        while True:
            self._safe_addstr(h - 1, 0, prompt + "".join(result), self._attr(5, True))
            self.stdscr.clrtoeol()
            self.stdscr.refresh()
            key = self.get_key()
            if key is None:
                continue
            if key == "ENTER":
                break
            if key in ("ESC", "RESIZE"):
                return ""
            if key == "BACKSPACE":
                if result:
                    result.pop()
            elif len(key) == 1 and key.isprintable():
                result.append(key)
        return "".join(result)

    def draw(
        self,
        containers: list["ContainerInfo"],
        sort_attr: str,
        sort_reverse: bool,
        filter_text: str,
        refresh_rate: float,
        tree_mode: bool,
        tree_data: str | None,
        selected_idx: int,
        details: str | None,
        show_help: bool,
        host_net_rx: int = 0,
        host_net_tx: int = 0,
    ) -> None:
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if h < 3 or w < 40:
            self.stdscr.refresh()
            return

        row = 0
        ts = self._ts()
        sort_str = f"{sort_attr}{'↓' if sort_reverse else '↑'}" if sort_attr else "none"
        net_str = f"NET ↓{fmt_bytes(host_net_rx)} ↑{fmt_bytes(host_net_tx)}"
        status = (
            f"fjtop | {ts} | {len(containers)} containers | {net_str} | "
            f"sort: {sort_str} | {refresh_rate:.1f}s"
        )
        if filter_text:
            status += f" | filter:/{filter_text}"
        status += "  H help | Q quit"
        self._safe_addstr(row, 0, status[: w - 1], self._attr(5, True))
        row += 1

        self._hline(row, w)
        row += 1

        if show_help:
            self._draw_help(row, h, w)
            self.stdscr.refresh()
            return

        if details:
            self._draw_details(row, h, w, containers, selected_idx, details)
            self.stdscr.refresh()
            return

        if not containers:
            self._safe_addstr(row, 0, "No firejail containers running.", self._attr(6))
            self.stdscr.refresh()
            return

        widths = _col_widths(w)
        self._draw_header(row, widths, sort_attr, sort_reverse)
        row += 1
        self._hline(row, w)
        row += 1

        if tree_mode and tree_data:
            self._draw_tree(row, h, w, containers, tree_data, widths)
        else:
            self._draw_rows(row, h, w, containers, widths, selected_idx)

        self.stdscr.refresh()

    def _ts(self) -> str:
        import time

        return time.strftime("%H:%M:%S")

    def _hline(self, row: int, w: int) -> None:
        with contextlib.suppress(curses.error):
            self.stdscr.addstr(row, 0, "─" * (w - 1), self._attr(5))

    def _draw_header(self, row: int, widths: dict[str, int], sort_attr: str, reverse: bool) -> None:
        arrow = "↓" if reverse else "↑"
        parts = []
        for i, (label, key, _) in enumerate(COLUMNS):
            width = widths[key]
            is_last = i == len(COLUMNS) - 1
            if key == sort_attr:
                parts.append(f"{label:<{width}}")
                if not is_last:
                    parts.append(arrow)
            else:
                parts.append(f"{label:<{width}}")
                if not is_last:
                    parts.append(" ")
        text = "".join(parts)
        self._safe_addstr(row, 0, text, self._attr(5, True) | curses.A_BOLD)

    def _draw_rows(
        self,
        row: int,
        h: int,
        w: int,
        containers: list["ContainerInfo"],
        widths: dict[str, int],
        selected_idx: int,
    ) -> None:
        for i, c in enumerate(containers):
            if row >= h - 1:
                break
            selected = i == selected_idx
            attr = curses.A_REVERSE if selected else 0

            parts = []
            for _label, key, _ in COLUMNS:
                width = widths[key]
                if key == "cpu_pct":
                    val = f"{c.cpu_pct:.1f}"
                elif key == "mem_pct":
                    val = f"{c.mem_pct:.1f}"
                elif key == "rss_bytes":
                    val = fmt_bytes(c.rss_bytes)
                elif key == "cpu_time_sec":
                    val = fmt_time(c.cpu_time_sec)
                elif key == "age_sec":
                    val = fmt_time(c.age_sec)
                elif key == "name":
                    val = c.name
                else:
                    val = str(getattr(c, key))
                parts.append(f"{val:<{width}}")
                if key != "name":
                    parts.append(" ")

            text = "".join(parts)[: w - 1]
            self._safe_addstr(row, 0, text, attr)

            # draw colored cpu/mem separately to apply colors
            if not selected:
                self._apply_color_over(row, containers[i], widths, w)
            row += 1

    def _apply_color_over(
        self, row: int, c: "ContainerInfo", widths: dict[str, int], w: int
    ) -> None:
        """Overwrite CPU% and MEM% columns with colored text."""
        x = 0
        for _label, key, _default_w in COLUMNS:
            width = widths[key]
            if key == "cpu_pct":
                text = f"{c.cpu_pct:.1f}".ljust(width)
                self._safe_addstr(row, x, text, self._cpu_attr(c.cpu_pct))
            elif key == "mem_pct":
                text = f"{c.mem_pct:.1f}".ljust(width)
                self._safe_addstr(row, x, text, self._mem_attr(c.mem_pct))
            x += width + 1
            if x >= w - 1:
                break

    def _draw_tree(
        self,
        row: int,
        h: int,
        w: int,
        containers: list["ContainerInfo"],
        tree_data: str,
        _widths: dict[str, int],
    ) -> None:
        tree_lines = tree_data.strip().split("\n")
        for tl in tree_lines:
            if row >= h - 1:
                break
            tl_stripped = tl.strip()
            if ":" not in tl_stripped:
                continue
            try:
                tree_pid = int(tl_stripped.split(":")[0])
            except ValueError:
                continue
            indent = len(tl) - len(tl.lstrip())
            for c in containers:
                if c.pid == tree_pid:
                    prefix = "  " * (indent // 2)
                    text = f"{prefix}{c.pid} {c.user} {c.name}"[: w - 1]
                    self._safe_addstr(row, 0, text, self._attr(5))
                    row += 1
                    break

    def _draw_help(self, row: int, h: int, w: int) -> None:
        lines = [
            "fjtop Help",
            "",
            "Sort",
            "  C CPU    M MEM",
            "  P PID    R RSS",
            "  A AGE    N name",
            "  Shift+key reverse",
            "",
            "Display",
            "  T        tree view",
            "  Enter    container details",
            "  /        filter",
            "  +/-      refresh rate",
            "  D        reset sort",
            "  H        this help",
            "",
            "General",
            "  Q / Esc  quit",
            "",
            "Press any key to close.",
        ]
        for line in lines:
            if row >= h - 1:
                break
            self._safe_addstr(row, 0, line[: w - 1], self._attr(5))
            row += 1

    def _draw_details(
        self,
        row: int,
        h: int,
        w: int,
        containers: list["ContainerInfo"],
        selected_idx: int,
        details: str,
    ) -> None:
        pid_str = str(containers[selected_idx].pid) if containers else "?"
        self._safe_addstr(row, 0, f"─ Container Details ({pid_str}) ─", self._attr(4))
        row += 1
        for dl in details.split("\n"):
            if row >= h - 1:
                break
            self._safe_addstr(row, 0, dl[: w - 1], self._attr(5))
            row += 1
        self._safe_addstr(row, 0, "Press any key to close.", self._attr(6))
