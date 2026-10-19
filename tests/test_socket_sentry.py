"""
Unit Tests for Sentinel+ Deterministic Socket Sentry
"""
import sys
from pathlib import Path

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from src.socket_sentry import audit_local_sockets, terminate_zombie_process, is_process_zombie_or_orphan

def test_audit_local_sockets_clean():
    # Auditing an unlikely port (e.g. 59999) should return clean status
    report = audit_local_sockets(target_ports=[59999])
    assert report.total_ports_scanned == 1
    assert report.active_listeners == 0
    assert report.zombies_detected == 0
    assert report.deterministic_math_valid is True
    assert "CLEAN" in report.summary_verdict

def test_terminate_zombie_process_2pc_guard():
    # Calling terminate without confirm=True MUST fail with TWO_PHASE_COMMIT_REQUIRED
    res = terminate_zombie_process(pid=99999, confirm=False)
    assert res["success"] is False
    assert res["error"] == "TWO_PHASE_COMMIT_REQUIRED"

def test_terminate_system_pid_guard():
    # Calling terminate on PID 1 or 0 MUST fail with ILLEGAL_PID
    res = terminate_zombie_process(pid=1, confirm=True)
    assert res["success"] is False
    assert res["error"] == "ILLEGAL_PID"

def test_is_process_zombie_negative():
    assert is_process_zombie_or_orphan(-1) is False
    assert is_process_zombie_or_orphan(0) is False
