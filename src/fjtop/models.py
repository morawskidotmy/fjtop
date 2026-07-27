from dataclasses import dataclass


@dataclass
class ContainerInfo:
    pid: int
    user: str
    name: str
    cpu_pct: float
    mem_pct: float
    rss_bytes: int
    cpu_time_sec: float
    age_sec: float
    net_rx_bytes: int
    net_tx_bytes: int
