# //Pranjal Das
"""
Streamable HTTP Model Context Protocol (MCP) Server (src/mcp_server.py)

Exposes infrastructure diagnostics and automated remediation via the Model Context Protocol:
- Streamable HTTP transport over Server-Sent Events (SSE) for real-time telemetry streaming.
- Standard JSON-RPC 2.0 tool endpoints (`tools/list`, `tools/call`).
- Fast-path deterministic router integration for sub-50ms conversational diagnostics.
- Zero-trust RBAC gatekeeper verifying Bearer tokens and limiting destructive actions.
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
    allow_credentials=False,
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
    },
    {
        "name": "sentinel_ebpf_socket_fsm",
        "description": "Deep eBPF/procfs audit across all 11 TCP states and Linux cgroups v2 memory pressure.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_ports": {
                    "type": "array",
                    "items": {"type": "integer"}
                }
            }
        }
    },
    {
        "name": "sentinel_predict_anomalies",
        "description": "Computes EWMA and rolling Z-Score statistics to predict memory leaks and socket exhaustion before crashes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_pids": {
                    "type": "array",
                    "items": {"type": "integer"}
                }
            }
        }
    },
    {
        "name": "sentinel_bedrock_mesh_query",
        "description": "Queries the resilient multi-model Bedrock mesh with automated rate limiting and circuit breaking.",
        "inputSchema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"}
            }
        }
    },
    {
        "name": "sentinel_cluster_fleet_audit",
        "description": "Audits distributed cluster topology across dev-local, staging-ecs, and production-k8s.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cluster_name": {"type": "string", "default": "all"}
            }
        }
    },
    {
        "name": "sentinel_verify_architecture_diagram",
        "description": "Uses Amazon Bedrock Nova Pro multimodal vision to parse architecture diagrams and verify against live sockets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "diagram_path": {"type": "string", "default": "architecture.png"}
            }
        }
    },
    {
        "name": "sentinel_generate_github_pr",
        "description": "Synthesizes an atomic unified diff patch and GitHub PR envelope for unclosed sockets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_file": {"type": "string", "default": "server.py"},
                "port": {"type": "integer", "default": 3000}
            }
        }
    },
    {
        "name": "sentinel_get_friction_log",
        "description": "Returns the complete 6-column Amazon Developer Friction Log and SDK enhancement RFC.",
        "inputSchema": {"type": "object"}
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
    Emits real-time telemetry heartbeats, active port findings, and MCP discovery events.
    """
    async def event_generator():
        # First emit standard MCP Streamable HTTP endpoint discovery event
        yield "event: endpoint\ndata: /mcp/call\n\n"

        client_connected = True
        step = 0
        while client_connected:
            if await request.is_disconnected():
                break

            step += 1
            # Dispatch procfs audit to thread pool to avoid blocking asyncio event loop
            report = await asyncio.to_thread(audit_local_sockets)
            payload = {
                "step": step,
                "timestamp": time.time(),
                "active_listeners": report.active_listeners,
                "zombies_detected": report.zombies_detected,
                "total_scanned": report.total_ports_scanned,
                "status": "NORMAL" if report.zombies_detected == 0 else "ALERT",
                "summary": report.summary_verdict,
                "findings": [f.model_dump() for f in report.findings]
            }

            yield f"data: {json.dumps(payload)}\n\n"
            # Periodic SSE comment ping to prevent proxy connection timeout
            yield ": keep-alive\n\n"
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
    Handles initialize, ping, tools/list, and tools/call requests with zero-trust security checks.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error: Invalid JSON-RPC payload"}}
        )

    jsonrpc_id = body.get("id", 1)
    method = body.get("method", "")
    params = body.get("params", {})

    # Protocol Lifecycle: initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": jsonrpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "Sentinel+ Alexa MCP Sentry", "version": "1.0.0"}
            }
        }

    # Protocol Lifecycle: notifications/initialized
    elif method == "notifications/initialized":
        return Response(status_code=204)

    # Protocol Lifecycle: ping
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": jsonrpc_id, "result": {}}

    # Method 1: tools/list
    elif method == "tools/list":
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

        # Zero-Trust Security Gate with Cluster Scoping
        cluster = arguments.get("cluster", "dev")
        sec_ctx = SecurityGatekeeper.verify_and_hydrate(authorization)
        auth_decision = SecurityGatekeeper.authorize_action(sec_ctx, tool_name, cluster=cluster)
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

        elif tool_name == "sentinel_ebpf_socket_fsm":
            from src.ebpf_sentry import audit_ebpf_socket_lifecycle
            ports = arguments.get("target_ports")
            ebpf_rep = audit_ebpf_socket_lifecycle(target_ports=ports)
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(ebpf_rep.model_dump())}]}
            }

        elif tool_name == "sentinel_predict_anomalies":
            from src.anomaly_engine import evaluate_system_anomalies
            pids = arguments.get("target_pids")
            anom_rep = evaluate_system_anomalies(active_process_pids=pids)
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(anom_rep.model_dump())}]}
            }

        elif tool_name == "sentinel_bedrock_mesh_query":
            from src.bedrock_mesh import BedrockResiliencyMesh
            prompt_str = arguments.get("prompt", "audit infrastructure")
            mesh = BedrockResiliencyMesh()
            res = mesh.dispatch_inference(prompt_str)
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(res.model_dump())}]}
            }

        elif tool_name == "sentinel_cluster_fleet_audit":
            from src.cluster_manager import DistributedFleetManager
            cname = arguments.get("cluster_name", "all")
            if cname == "all":
                fleet_rep = DistributedFleetManager.audit_entire_fleet()
                data = fleet_rep.model_dump()
            else:
                topo = DistributedFleetManager.get_cluster_topology(cname)
                data = topo.model_dump()
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(data)}]}
            }

        elif tool_name == "sentinel_verify_architecture_diagram":
            from src.vision_verifier import ArchitectureVisionVerifier
            verifier = ArchitectureVisionVerifier()
            rep = verifier.verify_diagram()
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(rep.model_dump())}]}
            }

        elif tool_name == "sentinel_generate_github_pr":
            from src.remediation_engine import DynamicRemediationEngine
            target_file = arguments.get("target_file", "server.py")
            port = arguments.get("port", 3000)
            pr = DynamicRemediationEngine.generate_socket_drain_patch(target_file=target_file, port=port)
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(pr.model_dump())}]}
            }

        elif tool_name == "sentinel_get_friction_log":
            from src.agent_hierarchy import SentinelOrchestrator
            orch = SentinelOrchestrator()
            log_entry = orch._build_friction_log()
            return {
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(log_entry.model_dump())}]}
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
