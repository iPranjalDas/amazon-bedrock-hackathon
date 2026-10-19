"""
Sentinel+ Deterministic System Sentry (src/socket_sentry.py)
Implements the Oracus AI "Hard Math First, LLM Second" principle:
Zero arithmetic or socket auditing is delegated to foundation models.
All OS metrics, ports, and zombie PIDs are computed deterministically in pure Python.
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

# Inject packages from Drive D if present
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    # Lightweight dataclass fallback
    from dataclasses import dataclass, field, asdict

if HAS_PYDANTIC:
    class SocketFinding(BaseModel):
        port: int
        protocol: str = "tcp"
        pid: int = 0
        process_name: str = "unknown"
        state: str = "LISTEN"
        is_stale_zombie: bool = False
        risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
        memory_rss_mb: float = 0.0
        details: str = ""

    class SystemSentryReport(BaseModel):
        timestamp: float
        total_ports_scanned: int
        active_listeners: int
        zombies_detected: int
        findings: List[SocketFinding]
        summary_verdict: str
        deterministic_math_valid: bool = True
else:
    @dataclass
    class SocketFinding:
        port: int
        protocol: str = "tcp"
        pid: int = 0
        process_name: str = "unknown"
        state: str = "LISTEN"
        is_stale_zombie: bool = False
        risk_level: str = "LOW"
        memory_rss_mb: float = 0.0
        details: str = ""

        def model_dump(self):
            return asdict(self)

    @dataclass
    class SystemSentryReport:
        timestamp: float
        total_ports_scanned: int
        active_listeners: int
        zombies_detected: int
        findings: List[Any]
        summary_verdict: str
        deterministic_math_valid: bool = True

        def model_dump(self):
            return asdict(self)


def get_process_memory_mb(pid: int) -> float:
    """Reads RSS memory in MB from procfs deterministically."""
    if pid <= 0:
        return 0.0
    try:
        statm_path = f"/proc/{pid}/statm"
        if os.path.exists(statm_path):
            with open(statm_path, "r") as f:
                parts = f.read().split()
                # 2nd field is resident set size in pages
                rss_pages = int(parts[1])
                page_size_kb = os.sysconf("SC_PAGE_SIZE") / 1024
                return round((rss_pages * page_size_kb) / 1024, 2)
    except Exception:
        pass
    return 0.0


def is_process_zombie_or_orphan(pid: int) -> bool:
    """Checks whether the process is an orphan child or zombie holding a port."""
    if pid <= 0:
        return False
    try:
        status_path = f"/proc/{pid}/status"
        if os.path.exists(status_path):
            with open(status_path, "r") as f:
                content = f.read()
                # If parent PID is 1 (init/systemd/wsl-init), it is orphaned
                for line in content.splitlines():
                    if line.startswith("PPid:"):
                        ppid = int(line.split()[1])
                        return ppid == 1
                    if line.startswith("State:") and "Z" in line:
                        return True
    except Exception:
        pass
    return False


def audit_local_sockets(target_ports: Optional[List[int]] = None) -> SystemSentryReport:
    """
    Deterministically audits local TCP sockets and listening ports.
    Default high-risk target ports: 3000 (React/Next), 5173 (Vite), 8000 (FastAPI), 8080 (Java/Tomcat)
    """
    if target_ports is None:
        target_ports = [3000, 5173, 8000, 8080, 8081, 9000, 3306, 5432]

    findings: List[SocketFinding] = []
    ports_map: Dict[int, Dict[str, Any]] = {}

    # Method 1: Probe via ss -tulpn
    try:
        cmd = ["ss", "-tulpn"]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "LISTEN" not in line and "tcp" not in line:
                continue
            for port in target_ports:
                # Matches :3000 or *:3000 or 127.0.0.1:3000
                if f":{port} " in line or f":{port}\t" in line:
                    pid = 0
                    pname = "unknown"
                    if "users:((" in line:
                        try:
                            meta = line.split("users:((")[1].split(")")[0]
                            parts = meta.split(",")
                            pname = parts[0].strip('"')
                            for part in parts:
                                if "pid=" in part:
                                    pid = int(part.replace("pid=", "").strip())
                        except Exception:
                            pass

                    ports_map[port] = {
                        "port": port,
                        "pid": pid,
                        "pname": pname,
                        "state": "LISTEN"
                    }
    except Exception:
        pass

    # Build findings
    zombie_count = 0
    for port in target_ports:
        if port in ports_map:
            info = ports_map[port]
            pid = info["pid"]
            pname = info["pname"]
            is_orphan = is_process_zombie_or_orphan(pid)
            mem_mb = get_process_memory_mb(pid)

            if is_orphan and pid > 0:
                zombie_count += 1
                risk = "CRITICAL" if port in [3000, 8000, 8080] else "HIGH"
                details = f"Orphan zombie process {pname} (PID {pid}) holding port {port} without parent."
            elif pid > 0:
                risk = "MEDIUM"
                details = f"Active service {pname} (PID {pid}) listening on port {port} ({mem_mb} MB RAM)."
            else:
                risk = "LOW"
                details = f"Port {port} bound by kernel socket without detectable userspace PID."

            finding = SocketFinding(
                port=port,
                protocol="tcp",
                pid=pid,
                process_name=pname,
                state="LISTEN",
                is_stale_zombie=is_orphan,
                risk_level=risk,
                memory_rss_mb=mem_mb,
                details=details
            )
            findings.append(finding)

    # Determine summary verdict deterministically
    if zombie_count > 0:
        summary = f"ALERT: {zombie_count} orphaned zombie process(es) holding critical ports."
    elif len(findings) > 0:
        summary = f"HEALTHY: {len(findings)} active listening service(s) monitored with zero zombies."
    else:
        summary = "CLEAN: All target inspection ports are free and unallocated."

    return SystemSentryReport(
        timestamp=time.time(),
        total_ports_scanned=len(target_ports),
        active_listeners=len(findings),
        zombies_detected=zombie_count,
        findings=findings,
        summary_verdict=summary,
        deterministic_math_valid=True
    )


def terminate_zombie_process(pid: int, confirm: bool = False, timeout_sec: float = 3.0) -> Dict[str, Any]:
    """
    Two-Phase Commit (2PC) termination gate.
    Requires explicit confirm=True to execute mutation.
    Executes graceful SIGTERM with timeout, falling back to SIGKILL.
    """
    if not confirm:
        return {
            "success": False,
            "error": "TWO_PHASE_COMMIT_REQUIRED",
            "message": f"Action blocked: Must explicitly confirm termination for PID {pid}."
        }

    if pid <= 1:
        return {
            "success": False,
            "error": "ILLEGAL_PID",
            "message": f"Refusing to terminate system PID {pid}."
        }

    try:
        # Phase 1: Graceful SIGTERM
        os.kill(pid, signal.SIGTERM)
        start_t = time.time()
        while time.time() - start_t < timeout_sec:
            if not os.path.exists(f"/proc/{pid}"):
                return {
                    "success": True,
                    "pid": pid,
                    "signal_used": "SIGTERM",
                    "elapsed_sec": round(time.time() - start_t, 3),
                    "message": f"Process {pid} terminated gracefully."
                }
            time.sleep(0.1)

        # Phase 2: Forceful SIGKILL fallback
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.2)
        is_gone = not os.path.exists(f"/proc/{pid}")
        return {
            "success": is_gone,
            "pid": pid,
            "signal_used": "SIGKILL",
            "message": f"Process {pid} terminated via SIGKILL." if is_gone else f"PID {pid} still lingering."
        }
    except ProcessLookupError:
        return {"success": True, "pid": pid, "message": f"Process {pid} already dead."}
    except PermissionError:
        return {"success": False, "pid": pid, "error": "PERMISSION_DENIED", "message": "Root or sudo required."}
    except Exception as e:
        return {"success": False, "pid": pid, "error": str(e)}
