"""
Sentinel+ Streamable HTTP MCP Server (src/mcp_server.py)
Official Model Context Protocol (MCP) Server for Alexa+:
- Streamable HTTP over Server-Sent Events (SSE)
- JSON-RPC 2.0 Tool Protocol (`tools/list` and `tools/call`)
- Sai Dual-Path Router Integration
- AegisAgent Multi-Agent Triad Coordination
- Zero-Trust OAuth2 Account Linking Guard
- Web Simulator Static Asset Mount
"""
import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.socket_sentry import audit_local_sockets, terminate_zombie_process
from src.router import route_and_execute
from src.agent_hierarchy import SentinelOrchestrator
from src.security_gate import SecurityGatekeeper
from src.apla_templates import build_apla_telemetry_document, build_audio_player_directive
from src.alexa_conversations import handle_dialog_api_invoked

app = FastAPI(
    title="Sentinel+ Alexa MCP Sentry",
    description="Autonomous Infrastructure & Code Sentry for Alexa+ with Model Context Protocol over Streamable HTTP",
    version="1.0.0"
)

# Enable CORS for Web Simulator
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Standard MCP Tool Definitions
MCP_TOOLS_MANIFEST = [
    {
        "name": "sentinel_audit_ports",
        "description": "Deterministically scans local listening ports and sockets using procfs without LLM hallucinations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_ports": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Specific ports to inspect (e.g. [3000, 8000])"
                }
            }
        }
    },
    {
        "name": "sentinel_inspect_zombies",
        "description": "Identifies orphaned child processes and lingering dev servers holding sockets in TIME_WAIT.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster": {"type": "string", "default": "dev"}
            }
        }
    },
    {
        "name": "sentinel_remediate_socket",
        "description": "Terminates lingering zombie PIDs using a Two-Phase Commit (2PC) security gate.",
        "inputSchema": {
            "type": "object",
            "required": ["pid", "confirmed"],
            "properties": {
                "pid": {"type": "integer", "description": "PID to terminate"},
                "confirmed": {"type": "boolean", "description": "Explicit confirmation flag for 2PC"}
            }
        }
    },
    {
        "name": "sentinel_agentic_audit",
        "description": "Runs the full AegisAgent/Sai multi-agent debate and stages a verified GitHub PR patch.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "default": "/mnt/d/amazon-bedrock-hackathon"}
            }
        }
    },
    {
        "name": "sentinel_get_apla_audio",
        "description": "Generates declarative APLA multi-track audio document with programmatic volume ducking.",
        "inputSchema": {
            "type": "object",
            "required": ["speech_text"],
            "properties": {
                "speech_text": {"type": "string"},
                "severity": {"type": "string", "default": "NORMAL"}
            }
        }
    }
]


@app.get("/health")
def health_check():
    """Deterministic Health Check Endpoint."""
    report = audit_local_sockets()
    return {
        "status": "HEALTHY",
        "service": "Sentinel+ Alexa MCP Server",
        "timestamp": time.time(),
        "active_listeners": report.active_listeners,
        "zombies_detected": report.zombies_detected,
        "protocol": "Model Context Protocol over Streamable HTTP (SSE)"
    }


@app.get("/sse")
async def sse_telemetry_stream(request: Request):
    """
    Streamable HTTP Server-Sent Events (SSE) channel.
    Emits real-time telemetry heartbeats and incident events to the Alexa+ Web Simulator.
    """
    async def event_generator():
        client_connected = True
        step = 0
        while client_connected:
            if await request.is_disconnected():
                break

            step += 1
            report = audit_local_sockets()
            payload = {
                "step": step,
                "timestamp": time.time(),
                "active_listeners": report.active_listeners,
                "zombies_detected": report.zombies_detected,
                "status": "NORMAL" if report.zombies_detected == 0 else "ALERT",
                "summary": report.summary_verdict
            }

            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(3.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/mcp/call")
async def handle_mcp_jsonrpc(request: Request, authorization: Optional[str] = Header(None)):
    """
    Standard JSON-RPC 2.0 Model Context Protocol Endpoint.
    Handles tools/list and tools/call requests with zero-trust security checks.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON-RPC payload")

    jsonrpc_id = body.get("id", 1)
    method = body.get("method", "")
    params = body.get("params", {})

    # Method 1: tools/list
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "result": {
                "tools": MCP_TOOLS_MANIFEST
            }
        }

    # Method 2: tools/call
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Zero-Trust Security Gate
        sec_ctx = SecurityGatekeeper.verify_and_hydrate(authorization)
        auth_decision = SecurityGatekeeper.authorize_action(sec_ctx, tool_name)
        if not auth_decision["authorized"]:
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "error": {
                    "code": -32001,
                    "message": auth_decision["error"],
                    "data": auth_decision
                }
            }

        # Dispatch Tool
        if tool_name == "sentinel_audit_ports":
            ports = arguments.get("target_ports")
            report = audit_local_sockets(target_ports=ports)
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(report.model_dump())}]}
            }

        elif tool_name == "sentinel_inspect_zombies":
            report = audit_local_sockets()
            zombies = [f for f in report.findings if f.is_stale_zombie]
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps([z.model_dump() for z in zombies])}]}
            }

        elif tool_name == "sentinel_remediate_socket":
            pid = arguments.get("pid")
            confirm = arguments.get("confirmed", False)
            res = terminate_zombie_process(pid=pid, confirm=confirm)
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(res)}]}
            }

        elif tool_name == "sentinel_agentic_audit":
            repo_path = arguments.get("repo_path", str(_REPO_ROOT))
            orchestrator = SentinelOrchestrator(repo_path=repo_path)
            session = orchestrator.run_multi_agent_audit()
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(session.model_dump())}]}
            }

        elif tool_name == "sentinel_get_apla_audio":
            speech_text = arguments.get("speech_text", "Sentinel telemetry online.")
            severity = arguments.get("severity", "NORMAL")
            apla_doc = build_apla_telemetry_document(speech_text=speech_text, severity=severity)
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(apla_doc)}]}
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "error": {"code": -32601, "message": f"Procedure not found: {tool_name}"}
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "error": {"code": -32600, "message": f"Unsupported JSON-RPC method: {method}"}
        }


@app.post("/alexa/converse")
async def alexa_voice_ingress(request: Request):
    """
    Ingress point for Alexa+ natural language queries and Web Simulator voice.
    Integrates Sai Dual-Path Router.
    """
    payload = await request.json()
    query = payload.get("query", "")
    confirm = payload.get("confirm", False)

    result = route_and_execute(query=query, confirm_destructive=confirm)
    return result


@app.post("/alexa/dialog-api")
async def alexa_conversations_dialog_api(request: Request):
    """
    Endpoint for official Alexa Conversations Dialog.API.Invoked requests.
    """
    envelope = await request.json()
    res = handle_dialog_api_invoked(envelope)
    return res


# Mount Web Simulator static files if present
_WEB_DIR = _REPO_ROOT / "web"
if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
