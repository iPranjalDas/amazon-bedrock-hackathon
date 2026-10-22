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


def test_magic_bytes_sniffer_png_jpeg_webp():
    import pytest
    from fastapi import HTTPException
    from src.mcp_server import validate_image_magic_bytes

    # Valid PNG
    assert validate_image_magic_bytes(b"\x89PNG\r\n\x1a\n12345678") == "png"

    # Valid JPEG
    assert validate_image_magic_bytes(b"\xff\xd8\xff123456789012") == "jpeg"

    # Valid WEBP
    assert validate_image_magic_bytes(b"RIFF\x00\x00\x00\x00WEBP1234") == "webp"

    # Invalid / Prohibited (SVG / XML)
    with pytest.raises(HTTPException) as excinfo:
        validate_image_magic_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
    assert excinfo.value.status_code == 415

    # Payload too small
    with pytest.raises(HTTPException) as excinfo:
        validate_image_magic_bytes(b"short")
    assert excinfo.value.status_code == 400


def test_download_patch_and_export_audit():
    import asyncio
    from src.mcp_server import download_patch_artifact, export_audit_trail_artifact

    # Test patch download
    patch_resp = asyncio.run(download_patch_artifact(port=3000))
    assert patch_resp.status_code == 200
    assert b"diff --git" in patch_resp.body or b"--- a/" in patch_resp.body
    assert "sentinel_patch_port_3000.patch" in patch_resp.headers["Content-Disposition"]

    # Test forensic audit export
    audit_resp = asyncio.run(export_audit_trail_artifact())
    assert audit_resp.status_code == 200
    assert "sentinel_forensic_audit.json" in audit_resp.headers["Content-Disposition"]


