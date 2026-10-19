"""
Unit Tests for AegisAgent Debate Hierarchy, Sai Critic, and EcoLafaek Sandbox
"""
import sys
from pathlib import Path

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from src.agent_hierarchy import SentinelOrchestrator

def test_multi_agent_audit_flow():
    orchestrator = SentinelOrchestrator(repo_path=str(_REPO_ROOT))
    session = orchestrator.run_multi_agent_audit()

    # Verify session integrity
    assert session.session_id.startswith("sentinel-")
    assert session.status == "ACTION_STAGED"
    assert len(session.trace_steps) == 3

    # Agent 1: Inspector
    step_1 = session.trace_steps[0]
    assert step_1.agent_name == "Inspector_Agent"
    assert step_1.confidence >= 0.95

    # Agent 2: Auditor Critic (Sai / AegisAgent pattern)
    step_2 = session.trace_steps[1]
    assert step_2.agent_name == "Auditor_Critic"
    assert session.critic_verdict.approved is True
    assert session.critic_verdict.risk_score <= 0.5

    # Agent 3: Remediation Engineer (EcoLafaek pattern)
    step_3 = session.trace_steps[2]
    assert step_3.agent_name == "Remediation_Engineer"
    assert session.remediation_patch is not None
    assert "SIGTERM" in session.remediation_patch.diff_content

    # Amazon Friction Log (+10% Bonus)
    assert session.friction_log is not None
    assert "Alexa+" in session.friction_log.task
