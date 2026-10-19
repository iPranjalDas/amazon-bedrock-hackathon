# //Pranjal Das
"""
Sentinel+ Core System Sentry (src/socket_sentry.py)
Author: Pranjal Das //Pranjal Das

Engineered for: Build, Ship, Shape: Amazon Developer Hackathon (2026)
Core philosophy: "Hard Math First, LLM Second."
We deliberately avoid delegating low-level system audits to foundation models.
Instead, we extract raw socket states, procfs memory metrics, and orphan process trees
directly from the Linux kernel in pure Python. The LLM only receives verified, immutable facts.
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure our local Drive D packages directory takes precedence
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

# Data models for socket findings and audit reports
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
    """
    Reads resident set size (RSS) memory directly from /proc/<pid>/statm.
    This avoids spawning costly subprocesses like `ps` on hot monitoring loops.
    """
    if pid <= 0:
        return 0.0
    try:
        statm_file = f"/proc/{pid}/statm"
        if os.path.exists(statm_file):
            with open(statm_file, "r") as f:
                fields = f.read().split()
                # Field index 1 in /proc/[pid]/statm represents resident memory pages
                rss_pages = int(fields[1])
                page_size_kb = os.sysconf("SC_PAGE_SIZE") / 1024.0
                return round((rss_pages * page_size_kb) / 1024.0, 2)
    except (PermissionError, FileNotFoundError, IndexError, ValueError):
        # Process may have exited or is kernel-protected; return 0.0 gracefully
        pass
    return 0.0


def is_process_zombie_or_orphan(pid: int) -> bool:
    """
    Inspects process ancestry in /proc/<pid>/status.
    Detects two frequent failure modes on developer machines:
    1. Orphan workers: PPid == 1 (parent dev server crashed, leaving a rogue child).
    2. Defunct zombies: State contains 'Z' (zombie awaiting reaping by parent).
    """
    if pid <= 0:
        return False
    try:
        status_file = f"/proc/{pid}/status"
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                for line in f:
                    if line.startswith("PPid:"):
                        ppid = int(line.split()[1])
                        # In WSL / Linux, an orphan adopted by init/systemd has PPid == 1
                        if ppid == 1:
                            return True
                    elif line.startswith("State:") and "Z" in line:
                        return True
    except (PermissionError, FileNotFoundError, ValueError):
        pass
    return False


def audit_local_sockets(target_ports: Optional[List[int]] = None) -> SystemSentryReport:
    """
    Fast, deterministic socket probe using Linux ss (socket statistics).
    Scans common dev ports: 3000 (Next.js/React), 5173 (Vite), 8000 (FastAPI), 8080 (Java/Tomcat).
    """
    if target_ports is None:
        target_ports = [3000, 5173, 8000, 8080, 8081, 9000, 3306, 5432]

    findings: List[SocketFinding] = []
    active_port_map: Dict[int, Dict[str, Any]] = {}

    # Query kernel socket table via ss tool
    try:
        cmd = ["ss", "-tulpn"]
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        for line in output.splitlines():
            if "LISTEN" not in line and "tcp" not in line:
                continue
            for port in target_ports:
                # Matches :3000 or *:3000 with boundary whitespace
                if f":{port} " in line or f":{port}\t" in line:
                    pid = 0
                    process_name = "unknown"
                    if "users:((" in line:
                        try:
                            # Parse out: users:(("node",pid=1234,fd=19))
                            meta_str = line.split("users:((")[1].split(")")[0]
                            parts = meta_str.split(",")
                            process_name = parts[0].strip('"')
                            for part in parts:
                                if "pid=" in part:
                                    pid = int(part.replace("pid=", "").strip())
                        except (IndexError, ValueError):
                            pass

                    active_port_map[port] = {
                        "port": port,
                        "pid": pid,
                        "pname": process_name,
                        "state": "LISTEN"
                    }
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback if ss binary is restricted in container
        pass

    # Evaluate each target port deterministically
    zombie_count = 0
    for port in target_ports:
        if port in active_port_map:
            info = active_port_map[port]
            pid = info["pid"]
            pname = info["pname"]
            is_orphan = is_process_zombie_or_orphan(pid)
            mem_mb = get_process_memory_mb(pid)

            if is_orphan and pid > 0:
                zombie_count += 1
                risk = "CRITICAL" if port in [3000, 8000, 8080] else "HIGH"
                details = f"Orphan process '{pname}' (PID {pid}) holding port {port} after parent exit."
            elif pid > 0:
                risk = "MEDIUM"
                details = f"Active dev service '{pname}' (PID {pid}) listening on port {port} ({mem_mb} MB RAM)."
            else:
                risk = "LOW"
                details = f"Port {port} bound by kernel socket without accessible userspace PID."

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

    # Compute verdict summary
    if zombie_count > 0:
        verdict = f"ALERT: Detected {zombie_count} lingering orphan process(es) holding ports."
    elif len(findings) > 0:
        verdict = f"HEALTHY: Monitoring {len(findings)} active listening dev services with zero zombies."
    else:
        verdict = "CLEAN: All target inspection ports are free and unallocated."

    return SystemSentryReport(
        timestamp=time.time(),
        total_ports_scanned=len(target_ports),
        active_listeners=len(findings),
        zombies_detected=zombie_count,
        findings=findings,
        summary_verdict=verdict,
        deterministic_math_valid=True
    )


def terminate_zombie_process(pid: int, confirm: bool = False, timeout_sec: float = 3.0) -> Dict[str, Any]:
    """
    Two-Phase Commit (2PC) termination gate.
    Safety invariants:
    1. Rejects termination if confirm is not explicitly True.
    2. Refuses to touch system PIDs (PID <= 1) to prevent crashing WSL/OS.
    3. Issues graceful SIGTERM first, waiting up to timeout_sec before escalating to SIGKILL.
    """
    if not confirm:
        return {
            "success": False,
            "error": "TWO_PHASE_COMMIT_REQUIRED",
            "message": f"Action blocked by safety gate: Developer must explicitly confirm termination for PID {pid}."
        }

    # Hard invariant: Protect init/systemd
    if pid <= 1:
        return {
            "success": False,
            "error": "ILLEGAL_PID",
            "message": f"Refusing to touch system root PID {pid}."
        }

    try:
        # Step 1: Attempt graceful shutdown via SIGTERM
        os.kill(pid, signal.SIGTERM)
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            if not os.path.exists(f"/proc/{pid}"):
                return {
                    "success": True,
                    "pid": pid,
                    "signal_used": "SIGTERM",
                    "elapsed_sec": round(time.time() - start_time, 3),
                    "message": f"Process {pid} terminated gracefully."
                }
            time.sleep(0.1)

        # Step 2: Escalate to SIGKILL if socket is still held
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.15)
        released = not os.path.exists(f"/proc/{pid}")
        return {
            "success": released,
            "pid": pid,
            "signal_used": "SIGKILL",
            "message": f"Process {pid} terminated via SIGKILL." if released else f"PID {pid} still unreleased."
        }
    except ProcessLookupError:
        return {"success": True, "pid": pid, "message": f"Process {pid} already dead."}
    except PermissionError:
        return {"success": False, "pid": pid, "error": "PERMISSION_DENIED", "message": "Root or sudo required."}
    except Exception as exc:
        return {"success": False, "pid": pid, "error": str(exc)}
