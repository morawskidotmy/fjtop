import argparse
import sys

from .collector import Collector
from .config import load_config
from .display import SORT_ALIASES, UI


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fjtop",
        description="top-like monitor for Firejail containers",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        default=1.0,
        help="refresh delay in seconds (default: 1.0)",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="path to config file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print raw /proc values for each container and exit",
    )
    return parser.parse_args()


def _run_debug(col: Collector) -> None:
    import json

    print("firejail containers:")
    containers = col.list_containers()
    for pid, user, name in containers:
        print(f"  pid={pid} user={user} name={name}")

    print("\nraw /proc values:")
    for pid, _user, _name in containers:
        raw = col.read_raw(pid)
        print(f"  pid={pid}:")
        print(json.dumps(raw, indent=4, default=str))

    print("\ncomputed container info:")
    info = col.collect(containers, __import__("time").time())
    for c in info:
        print(f"  pid={c.pid} age={c.age_sec:.1f}s cpu_pct={c.cpu_pct:.1f}%")


def _sort_key(c: object, attr: str) -> object:
    return getattr(c, attr, 0) or 0


def _apply_filter(containers: list, filter_text: str) -> list:
    if not filter_text:
        return containers
    ft = filter_text.lower()
    return [
        c for c in containers if ft in c.name.lower() or ft in c.user.lower() or ft in str(c.pid)
    ]


def _sorted_containers(containers: list, sort_attr: str, reverse: bool) -> list:
    attr = SORT_ALIASES.get(sort_attr, sort_attr)
    if not attr:
        return containers
    containers.sort(key=lambda c, a=attr: _sort_key(c, a), reverse=reverse)
    return containers


State = dict


def _show_details(state: State, col: Collector, containers: list) -> None:
    if containers:
        pid = containers[state["selected_idx"]].pid
        state["details"] = col.get_info(pid) or "(no info available)"


def _change_sort(state: State, key: str) -> None:
    key_l = key.lower()
    new_attr = SORT_ALIASES[key_l]
    if state["sort_attr"] == new_attr:
        state["sort_reverse"] = not state["sort_reverse"]
    else:
        state["sort_attr"] = new_attr
        state["sort_reverse"] = key.isupper()


def _handle_key(
    key: str,
    state: State,
    ui: UI,
    col: Collector,
    containers: list,
) -> bool:
    if key in ("q", "Q", "ESC"):
        return False

    if key == "h":
        state["show_help"] = not state["show_help"]
    elif key in ("t", "T"):
        state["tree_mode"] = not state["tree_mode"]
        state["details"] = None
    elif key == "ENTER":
        _show_details(state, col, containers)
    elif key == "/":
        state["filter_text"] = ui.read_filter()
    elif key == "+":
        state["refresh_rate"] = min(10.0, state["refresh_rate"] + 0.5)
    elif key == "-":
        state["refresh_rate"] = max(0.5, state["refresh_rate"] - 0.5)
    elif key in ("d", "D"):
        state["sort_attr"] = "cpu_pct"
        state["sort_reverse"] = False
    elif key in ("UP", "k") and containers:
        state["selected_idx"] = max(0, state["selected_idx"] - 1)
    elif key in ("DOWN", "j") and containers:
        state["selected_idx"] = min(len(containers) - 1, state["selected_idx"] + 1)
    elif len(key) == 1 and key.lower() in SORT_ALIASES:
        _change_sort(state, key)

    return True


def _run(ui: UI, col: Collector, args: argparse.Namespace) -> None:
    import time

    config = load_config(args.config)

    state: State = {
        "refresh_rate": args.delay or config["display"]["refresh_rate"],
        "sort_attr": config["display"]["sort_by"],
        "sort_reverse": config["display"]["sort_reverse"],
        "tree_mode": config["display"]["show_tree"],
        "filter_text": "",
        "selected_idx": 0,
        "details": None,
        "show_help": False,
    }
    prev_containers: list[tuple[int, str, str]] = []

    while True:
        now = time.time()

        containers_raw = col.list_containers()
        if containers_raw != prev_containers:
            state["selected_idx"] = 0
            state["details"] = None
            prev_containers = containers_raw

        containers = col.collect(containers_raw, now)
        containers = _apply_filter(containers, state["filter_text"])
        containers = _sorted_containers(containers, state["sort_attr"], state["sort_reverse"])

        if state["selected_idx"] >= len(containers):
            state["selected_idx"] = max(0, len(containers) - 1)

        tree_data = col.get_tree() if state["tree_mode"] else None
        host_net = col._read_host_net() or (0, 0)
        attr = SORT_ALIASES.get(state["sort_attr"], state["sort_attr"])

        ui.draw(
            containers=containers,
            sort_attr=attr,
            sort_reverse=state["sort_reverse"],
            filter_text=state["filter_text"],
            refresh_rate=state["refresh_rate"],
            tree_mode=state["tree_mode"],
            tree_data=tree_data,
            selected_idx=state["selected_idx"],
            details=state["details"],
            show_help=state["show_help"],
            host_net_rx=host_net[0],
            host_net_tx=host_net[1],
        )

        ui.stdscr.timeout(int(state["refresh_rate"] * 1000))
        key = ui.get_key()
        if key is None:
            continue

        if state["show_help"]:
            state["show_help"] = False
            continue

        if state["details"]:
            state["details"] = None
            continue

        if not _handle_key(key, state, ui, col, containers):
            break


def main() -> None:
    args = _parse_args()
    col = Collector()

    has_firejail, err = col.has_firejail()
    if not has_firejail:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    if args.debug:
        _run_debug(col)
        return

    if not sys.stdin.isatty():
        print("Error: fjtop requires an interactive terminal", file=sys.stderr)
        sys.exit(1)

    ui = UI()
    try:
        _run(ui, col, args)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        ui.cleanup()
