# //Pranjal Das
"""
Unit tests for MCP protocol lifecycle (initialize, ping, tools/list)
and router 2PC resolution for port draining.
"""
import pytest
from src.router import route_and_execute, classify_intent_deterministic
from src.mcp_server import MCP_TOOLS_MANIFEST


def test_mcp_manifest_contains_new_tools():
    tool_names = [t["name"] for t in MCP_TOOLS_MANIFEST]
    assert "sentinel_verify_architecture_diagram" in tool_names
    assert "sentinel_generate_github_pr" in tool_names
    assert "sentinel_get_friction_log" in tool_names
    assert "sentinel_audit_ports" in tool_names
    assert len(tool_names) >= 11


def test_router_drain_port_without_confirm():
    res = route_and_execute("drain port 3000", confirm_destructive=False)
    assert res["route"] == "destructive_action"
    assert res["status"] == "CONFIRMATION_REQUIRED"
    assert res["requires_2pc_confirm"] is True
    assert "port 3000" in res["speech_text"]


def test_router_drain_port_with_confirm_clean_exit():
    # When port 3000 has no process, it should cleanly return ERROR with clear message, not crash with TypeError
    res = route_and_execute("drain port 3000", confirm_destructive=True)
    assert res["route"] == "destructive_action"
    assert res["status"] in ["EXECUTED", "ERROR"]
    assert "PID" in res["speech_text"] or "port 3000" in res["speech_text"]


def test_router_natural_kill_pid_regex():
    decision = classify_intent_deterministic("kill 9999")
    assert decision.route == "destructive_action"
    assert decision.target_pid == 9999

    decision2 = classify_intent_deterministic("terminate process 8888")
    assert decision2.route == "destructive_action"
    assert decision2.target_pid == 8888


def test_router_verify_diagram_fast_path():
    res = route_and_execute("verify diagram")
    assert res["route"] == "fast_path"
    assert "Architecture verification" in res["result"]["speech_text"]
