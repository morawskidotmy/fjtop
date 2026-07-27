import os
import subprocess
from pathlib import Path

from .models import ContainerInfo


def _extract_name(cmd: str) -> str:
    """Return the actual application name from a firejail command line."""
    if cmd.startswith("firejail "):
        cmd = cmd[len("firejail ") :]
    if " -- " in cmd:
        cmd = cmd.split(" -- ", 1)[1].strip()
    parts = cmd.split()
    if not parts:
        return "unknown"
    for part in parts:
        if not part.startswith("-"):
            return Path(part).name
    return Path(parts[0]).name


def _uptime() -> float:
    try:
        with (Path("/proc/uptime")).open() as f:
            return float(f.read().split()[0])
    except OSError:
        return 0.0


class Collector:
    def __init__(self) -> None:
        self._clock_ticks: int = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        page_size: int = os.sysconf(os.sysconf_names["SC_PAGE_SIZE"])
        phys_pages: int = os.sysconf(os.sysconf_names["SC_PHYS_PAGES"])
        self._total_mem: int = phys_pages * page_size
        self._prev_cpu: dict[int, float] = {}

    @property
    def total_mem(self) -> int:
        return self._total_mem

    def has_firejail(self) -> tuple[bool, str]:
        try:
            subprocess.run(["firejail", "--list"], capture_output=True, timeout=5)
            return True, ""
        except FileNotFoundError:
            return False, "firejail not found in $PATH"
        except PermissionError:
            return False, "permission denied running firejail"

    def list_containers(self) -> list[tuple[int, str, str]]:
        try:
            r = subprocess.run(
                ["firejail", "--list"],
                capture_output=True,
                timeout=5,
            )
        except (FileNotFoundError, PermissionError):
            return []
        if r.returncode != 0:
            return []

        out = r.stdout.decode().strip()
        if not out:
            return []

        cs: list[tuple[int, str, str]] = []
        for line in out.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            user = parts[1]
            cmd = parts[3].strip()
            name = _extract_name(cmd)
            cs.append((pid, user, name))
        return cs

    def collect(self, containers: list[tuple[int, str, str]], now: float) -> list[ContainerInfo]:
        results: list[ContainerInfo] = []
        uptime_sec = _uptime()

        for pid, user, name in containers:
            try:
                descendants = self._get_descendants(pid)
                if not descendants:
                    continue

                total_utime = 0
                total_stime = 0
                total_rss = 0
                root_starttime = None

                for dpid in descendants:
                    status = self._read_status(dpid)
                    if status is None:
                        continue

                    stat_data = self._read_stat(dpid)
                    if stat_data is None:
                        continue

                    utime, stime, starttime = stat_data
                    total_utime += utime
                    total_stime += stime

                    if dpid == pid:
                        root_starttime = starttime

                    rss_str = status.get("VmRSS", "0 kB").split()[0]
                    try:
                        rss = int(rss_str) * 1024
                    except (ValueError, TypeError):
                        rss = 0
                    total_rss += rss

                if root_starttime is None:
                    continue

                cpu_total = total_utime + total_stime

                net_data = self._read_net(pid)
                net_rx = net_data[0] if net_data else 0
                net_tx = net_data[1] if net_data else 0
            except (OSError, ValueError, IndexError):
                continue

            prev_cpu = self._prev_cpu.get(pid, 0.0)
            dt = now - prev_cpu if prev_cpu else 0.0

            if prev_cpu and dt > 0:
                dcpu = cpu_total - prev_cpu
                cpu_pct = dcpu / self._clock_ticks / dt * 100
            else:
                cpu_pct = 0.0
            self._prev_cpu[pid] = cpu_total

            mem_pct = total_rss / self._total_mem * 100 if self._total_mem else 0

            age = uptime_sec - root_starttime / self._clock_ticks

            results.append(
                ContainerInfo(
                    pid=pid,
                    user=user,
                    name=name,
                    cpu_pct=cpu_pct,
                    mem_pct=mem_pct,
                    rss_bytes=total_rss,
                    cpu_time_sec=cpu_total / self._clock_ticks,
                    age_sec=age,
                    net_rx_bytes=net_rx,
                    net_tx_bytes=net_tx,
                )
            )
        return results

    def _read_status(self, pid: int) -> dict[str, str] | None:
        try:
            with (Path(f"/proc/{pid}/status")).open() as f:
                d: dict[str, str] = {}
                for line in f:
                    if ":" in line:
                        k, _, v = line.partition(":")
                        d[k.strip()] = v.strip()
                return d
        except OSError:
            return None

    @staticmethod
    def _parse_stat(data: str) -> tuple[int, int, int] | None:
        # The command name (field 2) is wrapped in parentheses and may contain
        # spaces, so split only after the closing ')' to avoid index drift.
        close = data.rfind(")")
        if close == -1:
            return None
        fields = data[close + 1 :].split()
        utime = int(fields[11])  # field 14 (utime)
        stime = int(fields[12])  # field 15 (stime)
        starttime = int(fields[19])  # field 22 (starttime)
        return utime, stime, starttime

    def _read_stat(self, pid: int) -> tuple[int, int, int] | None:
        try:
            with (Path(f"/proc/{pid}/stat")).open() as f:
                data = f.read()
            return self._parse_stat(data)
        except (OSError, IndexError, ValueError):
            return None

    def read_raw(self, pid: int) -> dict[str, object]:
        """Return raw /proc values for debugging."""
        raw: dict[str, object] = {"pid": pid}
        stat = self._read_stat(pid)
        if stat:
            raw["utime"] = stat[0]
            raw["stime"] = stat[1]
            raw["starttime"] = stat[2]
        raw["status"] = self._read_status(pid)
        raw["net"] = self._read_net(pid)
        return raw

    def _read_host_net(self) -> tuple[int, int] | None:
        try:
            with Path("/proc/net/dev").open() as f:
                total_rx = 0
                total_tx = 0
                for line in f:
                    if ":" not in line:
                        continue
                    iface, rest = line.split(":", 1)
                    if iface.strip() == "lo":
                        continue
                    fields = rest.split()
                    if len(fields) >= 10:
                        total_rx += int(fields[0])
                        total_tx += int(fields[8])
            return total_rx, total_tx
        except OSError:
            return None

    def _get_descendants(self, pid: int) -> list[int]:
        """Recursively get all descendant PIDs for a given PID."""
        descendants = [pid]
        children_path = Path(f"/proc/{pid}/task/{pid}/children")
        try:
            children_str = children_path.read_text().strip()
            if children_str:
                for child_pid_str in children_str.split():
                    try:
                        child_pid = int(child_pid_str)
                        descendants.extend(self._get_descendants(child_pid))
                    except (ValueError, OSError):
                        continue
        except OSError:
            pass
        return descendants

    def _read_net(self, pid: int) -> tuple[int, int] | None:
        try:
            with (Path(f"/proc/{pid}/net/dev")).open() as f:
                total_rx = 0
                total_tx = 0
                for line in f:
                    if ":" not in line:
                        continue
                    iface, rest = line.split(":", 1)
                    if iface.strip() == "lo":
                        continue
                    fields = rest.split()
                    if len(fields) >= 10:
                        total_rx += int(fields[0])
                        total_tx += int(fields[8])
            return total_rx, total_tx
        except OSError:
            return None

    def get_tree(self) -> str | None:
        try:
            r = subprocess.run(
                ["firejail", "--tree"],
                capture_output=True,
                timeout=5,
            )
            if r.returncode != 0:
                return None
            return r.stdout.decode()
        except (FileNotFoundError, PermissionError):
            return None

    def get_info(self, pid: int) -> str | None:
        try:
            r = subprocess.run(
                ["firejail", "--info", str(pid)],
                capture_output=True,
                timeout=5,
            )
            if r.returncode != 0:
                return None
            return r.stdout.decode()
        except (FileNotFoundError, PermissionError):
            return None
