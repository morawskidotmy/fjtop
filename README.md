<div align="center">

# fjtop

**top-like monitor for Firejail containers**

[![Python](https://img.shields.io/badge/Python-≥3.11-3776AB?style=flat-square&logo=python)](https://python.org)
[![Ruff](https://img.shields.io/badge/Ruff-ok-5ed9c7?style=flat-square)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](LICENSE)

[Installation](#installation) • [Usage](#usage) • [Keyboard Shortcuts](#keyboard-shortcuts) • [Columns](#columns) • [Configuration](#configuration)

</div>

A live-updating terminal dashboard for monitoring Firejail sandboxes. Shows aggregated CPU, memory, and runtime metrics for each container (including all child processes), plus host network totals in the status bar.

## Installation

### With uv (recommended)

```bash
uv tool install git+https://github.com/morawskidotmy/fjtop
```

### From source

```bash
git clone https://github.com/morawskidotmy/fjtop && cd fjtop
uv tool install .
```

### Dependencies

- Python ≥ 3.11
- firejail must be installed and in `$PATH`

## Usage

```bash
fjtop
```

Press `q` or `Ctrl+C` to quit. The display refreshes every second.

> [!TIP]
> Run `fjtop` as your own user — it reads `/proc/<pid>` entries which are world-readable for your own processes. No root required.

### Options

```
usage: fjtop [-h] [-d DELAY] [-c CONFIG] [--debug]

options:
  -h, --help              show help message and exit
  -d, --delay DELAY       refresh delay in seconds (default: 1.0)
  -c, --config CONFIG     path to config file
  --debug                 print raw /proc values and exit
```

> [!TIP]
> Use `fjtop --debug` to diagnose parsing or metric issues. It prints raw values from `/proc/<pid>/status`, `/proc/<pid>/stat`, and `/proc/<pid>/net/dev` for each container, along with the computed ages and CPU percentages.

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `c` / `C` | Sort by CPU% (ascending / descending) |
| `m` / `M` | Sort by MEM% |
| `p` / `P` | Sort by PID |
| `r` / `R` | Sort by RSS |
| `a` / `A` | Sort by AGE |
| `n` / `N` | Sort by process name |
| `t` / `T` | Toggle tree view |
| `↑` / `↓` or `k` / `j` | Move selection up/down |
| `d` / `D` | Reset to default sort (CPU) |
| `/` | Enter filter mode (type to filter by name, user, or PID) |
| `Enter` | Show container details (`firejail --info <pid>`) |
| `+` / `-` | Increase / decrease refresh rate (0.5s – 10s) |
| `h` | Toggle help screen |
| `q` / `Esc` | Quit |

## Columns

| Column | Source | Description |
|---|---|---|
| `PID` | `firejail --list` | Process ID of the Firejail process |
| `USER` | `firejail --list` | Owner of the sandbox |
| `CPU%` | `/proc/<pid>/*/stat` | Aggregated CPU usage across all container processes (color-coded) |
| `MEM%` | `/proc/<pid>/*/status` | Aggregated RSS / total physical memory (color-coded) |
| `RSS` | `/proc/<pid>/*/status` | Aggregated resident set size across all container processes |
| `TIME+` | `/proc/<pid>/*/stat` | Aggregated cumulative CPU time consumed |
| `AGE` | `/proc/<pid>/stat` | Wall-clock time since sandbox started |
| `PROCESS` | `firejail --list` | Application running inside the sandbox |

## Configuration

fjtop supports a TOML config file at `~/.config/fjtop/config.toml`:

```toml
[display]
refresh_rate = 2.0
sort_by = "mem_pct"
sort_reverse = false
show_tree = false
```

## How it works

`fjtop` parses `firejail --list` to discover active containers, then reads stats from `/proc/<pid>/task/<pid>/children` to find all processes in each container. CPU, memory, and time metrics are aggregated across all descendant processes — no elevated privileges needed. The application name shown in the `PROCESS` column is extracted from the firejail command line, so `firejail --args -- /path/to/app` displays as `app`.

The UI is built with Python's `curses` module for proper terminal handling, keyboard input, and colors. CPU usage is computed as a delta between ticks, and host network totals are shown in the status bar from `/proc/net/dev`. Color thresholds can be customized in the config file.

## Development

```bash
git clone https://github.com/morawskidotmy/fjtop && cd fjtop
uv sync              # create venv and install deps
uv run pytest        # run tests
uv run ruff check .  # lint
uv run ruff format . # format
```
