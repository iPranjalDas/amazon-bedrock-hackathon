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
