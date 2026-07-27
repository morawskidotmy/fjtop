import tomllib
from pathlib import Path

DEFAULT_CONFIG = {
    "display": {
        "refresh_rate": 1.0,
        "sort_by": "cpu_pct",
        "sort_reverse": False,
        "color": True,
        "show_tree": False,
    },
    "columns": {
        "pid": True,
        "user": True,
        "cpu_pct": True,
        "mem_pct": True,
        "rss_bytes": True,
        "cpu_time_sec": True,
        "age_sec": True,
        "net_rx_bytes": False,
        "net_tx_bytes": False,
    },
}


def load_config(path: str | None = None) -> dict:
    p = Path(path) if path else Path.home() / ".config" / "fjtop" / "config.toml"

    config = DEFAULT_CONFIG.copy()
    config["display"] = DEFAULT_CONFIG["display"].copy()
    config["columns"] = DEFAULT_CONFIG["columns"].copy()

    if not p.exists():
        return config

    try:
        data = tomllib.loads(p.read_text())
        for section in ("display", "columns"):
            if section in data:
                config[section].update(data[section])
    except (tomllib.TOMLDecodeError, OSError):
        pass

    return config
