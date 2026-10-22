# //Pranjal Das
"""
Unit Tests for Sentinel+ Dual-Path Ingress Router (Sai Pattern)
"""
import sys
from pathlib import Path

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from src.router import classify_intent_deterministic, route_and_execute

def test_classify_fast_path():
    decision = classify_intent_deterministic("is port 3000 free?")
    assert decision.route == "fast_path"
    assert decision.target_port == 3000
    assert decision.confidence >= 0.90
    assert decision.requires_2pc_confirm is False

def test_classify_destructive_gate():
    decision = classify_intent_deterministic("kill PID 4512")
    assert decision.route == "destructive_action"
    assert decision.target_pid == 4512
    assert decision.requires_2pc_confirm is True

def test_classify_agentic_audit():
    decision = classify_intent_deterministic("conduct a security vulnerability audit on the repo")
    assert decision.route == "agentic_audit"
    assert decision.requires_2pc_confirm is False

def test_fast_path_latency_sub_50ms():
    res = route_and_execute("check port 8000 status")
    assert res["route"] == "fast_path"
    assert res["result"]["success"] is True
    assert res["result"]["latency_ms"] < 50.0  # Must be fast!
    assert "monitored" in res["result"]["speech_text"].lower() or "ports" in res["result"]["speech_text"].lower()

def test_destructive_gate_blocks_without_confirm():
    res = route_and_execute("kill PID 1234", confirm_destructive=False)
    assert res["route"] == "destructive_action"
    assert res["status"] == "CONFIRMATION_REQUIRED"
    assert res["requires_2pc_confirm"] is True

def test_conversational_bedrock_chat():
    res = route_and_execute("hello, how are you?")
    assert res["route"] == "conversational_bedrock"
    assert res["status"] == "CONVERSATIONAL_REPLY"
    assert "sentinel+" in res["speech_text"].lower() or "amazon" in res["speech_text"].lower()
    assert res["latency_ms"] < 200.0

def test_conversational_questions():
    res = route_and_execute("who are you and what do you do?")
    assert res["route"] == "conversational_bedrock"
    assert len(res["speech_text"]) > 20
    assert "nova" in res["model"].lower()

def test_multi_turn_slot_carryover():
    sid = "session-carryover-test-01"
    # Turn 1: query port 3000
    res1 = route_and_execute("is port 3000 free?", session_id=sid)
    assert res1["route"] == "fast_path"
    assert res1["session_state"]["last_queried_port"] == 3000

    # Turn 2: anaphoric reference "kill it"
    res2 = route_and_execute("kill it", session_id=sid)
    assert res2["route"] == "destructive_action"
    assert res2["requires_2pc_confirm"] is True
    assert res2["session_state"]["confirmation_pending"] is True
    assert "port 3000" in res2["speech_text"]

    # Turn 3: affirmative 2PC confirmation "confirm"
    res3 = route_and_execute("confirm", session_id=sid)
    assert res3["route"] == "destructive_action"
    assert res3["status"] in ["EXECUTED", "ERROR"]

def test_session_manager_lru_limits():
    from src.router import SessionManager
    mgr = SessionManager(max_sessions=5, ttl_seconds=10)
    for i in range(10):
        s = mgr.get_or_create(f"sess-{i}")
        s.last_queried_port = 8000 + i
    
    assert len(mgr._sessions) == 5
    # The oldest (0..4) should have been evicted
    assert "sess-0" not in mgr._sessions
    assert "sess-9" in mgr._sessions

