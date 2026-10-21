# //Pranjal Das
"""
eBPF-Inspired Kernel Socket Lifecycle & cgroups v2 Inspector (src/ebpf_sentry.py)
Author: Pranjal Das //Pranjal Das

Reads raw TCP socket tables and cgroup memory limits directly from the Linux kernel.
Instead of relying on high-level tools like netstat or lsof (which spawn expensive
subprocesses), this module parses /proc/net/tcp and /sys/fs/cgroup directly in pure Python.

Key capabilities:
1. TCP Finite State Machine (FSM) tracking across all 11 RFC 793 connection states.
2. Differentiates between TIME_WAIT (normal kernel drain) and CLOSE_WAIT (unclosed app handles).
3. Evaluates cgroups v2 memory pressure to predict OOM kills before the kernel invokes them.
"""
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    from dataclasses import dataclass, asdict

# RFC 793 / Linux Kernel tcp_states.h mapping
TCP_STATE_MAP = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING"
}

if HAS_PYDANTIC:
    class TCPSocketEntry(BaseModel):
        local_ip: str
        local_port: int
        remote_ip: str
        remote_port: int
        state: str
        inode: int
        is_stale: bool = False

    class CgroupMemoryMetrics(BaseModel):
        cgroup_version: str
        current_bytes: int
        max_bytes: Optional[int] = None
        usage_percent: float
        memory_pressure_risk: str  # "NOMINAL", "ELEVATED", "CRITICAL"

    class SocketLifecycleReport(BaseModel):
        timestamp: float
        target_ports: List[int]
        total_sockets_scanned: int
        state_distribution: Dict[str, int]
        monitored_entries: List[TCPSocketEntry]
        cgroup_metrics: CgroupMemoryMetrics
        health_verdict: str
        requires_immediate_drain: bool
else:
    class TCPSocketEntry:
        def __init__(self, local_ip, local_port, remote_ip, remote_port, state, inode, is_stale=False):
            self.local_ip = local_ip
            self.local_port = local_port
            self.remote_ip = remote_ip
            self.remote_port = remote_port
            self.state = state
            self.inode = inode
            self.is_stale = is_stale
        def model_dump(self):
            return self.__dict__

    class CgroupMemoryMetrics:
        def __init__(self, cgroup_version, current_bytes, max_bytes, usage_percent, memory_pressure_risk):
            self.cgroup_version = cgroup_version
            self.current_bytes = current_bytes
            self.max_bytes = max_bytes
            self.usage_percent = usage_percent
            self.memory_pressure_risk = memory_pressure_risk
        def model_dump(self):
            return self.__dict__

    class SocketLifecycleReport:
        def __init__(self, timestamp, target_ports, total_sockets_scanned, state_distribution,
                     monitored_entries, cgroup_metrics, health_verdict, requires_immediate_drain):
            self.timestamp = timestamp
            self.target_ports = target_ports
            self.total_sockets_scanned = total_sockets_scanned
            self.state_distribution = state_distribution
            self.monitored_entries = monitored_entries
            self.cgroup_metrics = cgroup_metrics
            self.health_verdict = health_verdict
            self.requires_immediate_drain = requires_immediate_drain
        def model_dump(self):
            return {
                "timestamp": self.timestamp,
                "target_ports": self.target_ports,
                "total_sockets_scanned": self.total_sockets_scanned,
                "state_distribution": self.state_distribution,
                "monitored_entries": [e.model_dump() for e in self.monitored_entries],
                "cgroup_metrics": self.cgroup_metrics.model_dump(),
                "health_verdict": self.health_verdict,
                "requires_immediate_drain": self.requires_immediate_drain
            }


def _hex_to_ip_port(hex_str: str) -> Tuple[str, int]:
    """
    Decodes Linux /proc/net/tcp address representations.
    Example: '0100007F:1F90' -> ('127.0.0.1', 8080)
    """
    try:
        ip_hex, port_hex = hex_str.split(":")
        port = int(port_hex, 16)
        # Linux stores IPv4 in little-endian order in /proc/net/tcp
        ip_parts = [str(int(ip_hex[i:i+2], 16)) for i in (6, 4, 2, 0)]
        ip = ".".join(ip_parts)
        return ip, port
    except Exception:
        return "0.0.0.0", 0


def parse_proc_net_tcp() -> List[Dict[str, Any]]:
    """
    Directly parses /proc/net/tcp and /proc/net/tcp6 without shelling out.
    Returns decoded socket records with IP, port, FSM state, and inode.
    """
    records = []
    candidates = ["/proc/net/tcp", "/proc/net/tcp6"]

    for proc_path in candidates:
        if not os.path.exists(proc_path):
            continue
        try:
            with open(proc_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[1:]:  # Skip header
                parts = line.strip().split()
                if len(parts) < 10:
                    continue
                local_ip, local_port = _hex_to_ip_port(parts[1])
                remote_ip, remote_port = _hex_to_ip_port(parts[2])
                raw_state = parts[3].upper()
                state_name = TCP_STATE_MAP.get(raw_state, f"UNKNOWN_{raw_state}")
                inode = int(parts[9]) if parts[9].isdigit() else 0

                records.append({
                    "local_ip": local_ip,
                    "local_port": local_port,
                    "remote_ip": remote_ip,
                    "remote_port": remote_port,
                    "state": state_name,
                    "inode": inode
                })
        except (PermissionError, FileNotFoundError):
            continue

    return records


def read_cgroup_memory_pressure() -> CgroupMemoryMetrics:
    """
    Probes Linux cgroups v2 interface for memory saturation metrics.
    Gracefully calculates fallback heuristics if running on bare WSL2 without hard cgroup limits.
    """
    cgroup_base = Path("/sys/fs/cgroup")
    current_bytes = 0
    max_bytes = None

    # Probe cgroups v2
    cur_file = cgroup_base / "memory.current"
    max_file = cgroup_base / "memory.max"

    if cur_file.exists():
        try:
            val = cur_file.read_text().strip()
            if val.isdigit():
                current_bytes = int(val)
        except Exception:
            pass

    if max_file.exists():
        try:
            val = max_file.read_text().strip()
            if val.isdigit():
                max_bytes = int(val)
        except Exception:
            pass

    # Heuristic fallback if running outside a restricted container
    if current_bytes == 0:
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                        max_bytes = total_kb * 1024
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
                        if max_bytes:
                            current_bytes = max_bytes - (avail_kb * 1024)
        except Exception:
            current_bytes = 512 * 1024 * 1024  # 512 MB nominal baseline
            max_bytes = 4096 * 1024 * 1024     # 4 GB baseline

    max_val = max_bytes if (max_bytes and max_bytes > 0) else (current_bytes * 2)
    usage_percent = round((current_bytes / max_val) * 100, 2) if max_val else 25.0

    if usage_percent > 88.0:
        risk = "CRITICAL"
    elif usage_percent > 70.0:
        risk = "ELEVATED"
    else:
        risk = "NOMINAL"

    return CgroupMemoryMetrics(
        cgroup_version="v2" if cur_file.exists() else "procfs_emulated",
        current_bytes=current_bytes,
        max_bytes=max_bytes,
        usage_percent=usage_percent,
        memory_pressure_risk=risk
    )


def audit_ebpf_socket_lifecycle(target_ports: Optional[List[int]] = None) -> SocketLifecycleReport:
    """
    Audits the entire TCP state machine for monitored development ports.
    Flags hazardous states:
    - High CLOSE_WAIT: Application leaked a socket connection and failed to close its file descriptor.
    - Excessive TIME_WAIT: Client socket churn exhausting local ephemeral ports.
    """
    if target_ports is None:
        target_ports = [3000, 5173, 8000, 8080]

    raw_records = parse_proc_net_tcp()
    state_distribution: Dict[str, int] = {}
    monitored: List[TCPSocketEntry] = []

    for rec in raw_records:
        st = rec["state"]
        state_distribution[st] = state_distribution.get(st, 0) + 1

        port = rec["local_port"]
        if port in target_ports:
            # Sockets in CLOSE_WAIT or multiple TIME_WAITs on active dev ports represent leak risks
            is_stale = st in ["CLOSE_WAIT", "LAST_ACK"]
            monitored.append(TCPSocketEntry(
                local_ip=rec["local_ip"],
                local_port=port,
                remote_ip=rec["remote_ip"],
                remote_port=rec["remote_port"],
                state=st,
                inode=rec["inode"],
                is_stale=is_stale
            ))

    cgroup_data = read_cgroup_memory_pressure()
    close_wait_count = sum(1 for m in monitored if m.state == "CLOSE_WAIT")
    requires_drain = close_wait_count > 0 or cgroup_data.memory_pressure_risk == "CRITICAL"

    if close_wait_count > 0:
        verdict = f"ALERT: Detected {close_wait_count} socket(s) in CLOSE_WAIT leak state. Immediate drain advised."
    elif len(monitored) > 0:
        verdict = f"HEALTHY: Monitored {len(monitored)} socket connection(s) across target dev ports."
    else:
        verdict = "QUIET: No active network sockets currently bound to target dev ports."

    return SocketLifecycleReport(
        timestamp=time.time(),
        target_ports=target_ports,
        total_sockets_scanned=len(raw_records),
        state_distribution=state_distribution,
        monitored_entries=monitored,
        cgroup_metrics=cgroup_data,
        health_verdict=verdict,
        requires_immediate_drain=requires_drain
    )
