# //Pranjal Das
"""
Sentinel+ Ingress Router (src/router.py)
Author: Pranjal Das //Pranjal Das

Engineered for: Build, Ship, Shape: Amazon Developer Hackathon (2026)
Design pattern: Dual-Path Ingress Router.
Voice assistants feel sluggish when simple queries ("is port 3000 free?") trigger
a 3-second multi-turn LLM inference loop. We bifurcate the ingress:
1. Fast Path (< 10ms): Simple status and port queries execute immediately in Python.
2. Destructive 2PC Gate: Catches kill/drain requests and pauses for user confirmation.
3. Agentic Path: Deep multi-turn investigation only when deep code/repo reasoning is asked.
"""
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from src.socket_sentry import audit_local_sockets, terminate_zombie_process

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

if HAS_PYDANTIC:
    class RoutingDecision(BaseModel):
        route: str  # "fast_path", "agentic_audit", "destructive_action"
        intent_category: str
        confidence: float
        requires_2pc_confirm: bool = False
        target_pid: Optional[int] = None
        target_port: Optional[int] = None
        execution_plan: str
        raw_query: str

    class FastPathResult(BaseModel):
        success: bool
        route: str = "fast_path"
        latency_ms: float
        speech_text: str
        data: Dict[str, Any]
else:
    class RoutingDecision:
        def __init__(self, route, intent_category, confidence, requires_2pc_confirm=False,
                     target_pid=None, target_port=None, execution_plan="", raw_query=""):
            self.route = route
            self.intent_category = intent_category
            self.confidence = confidence
            self.requires_2pc_confirm = requires_2pc_confirm
            self.target_pid = target_pid
            self.target_port = target_port
            self.execution_plan = execution_plan
            self.raw_query = raw_query

        def model_dump(self):
            return self.__dict__

    class FastPathResult:
        def __init__(self, success, latency_ms, speech_text, data, route="fast_path"):
            self.success = success
            self.route = route
            self.latency_ms = latency_ms
            self.speech_text = speech_text
            self.data = data

        def model_dump(self):
            return self.__dict__


# High-frequency developer status phrases matched via regex for instant response
FAST_PATH_PATTERNS = [
    (r"\b(ebpf|tcp state|socket fsm|cgroups?)\b", "ebpf_trace"),
    (r"\b(anomal|leak|predict|z-?score|exhaustion)\b", "anomaly_prediction"),
    (r"\b(fleet|cluster|staging|production|k8s|kubernetes|ecs)\b", "cluster_fleet"),
    (r"\b(bedrock|mesh|nova|claude.*fallback|resilience)\b", "bedrock_mesh"),
    (r"\b(check|status|health|ping|listeners?|open ports?|is.*free|is.*running)\b", "port_status"),
    (r"\b(who.*listening|what.*running|system sentry info)\b", "system_info"),
    (r"\b(list zombies?|find zombies?|show processes?)\b", "list_zombies")
]

# Sensitive operations that must be intercepted before mutating system state
DESTRUCTIVE_PATTERNS = [
    (r"\b(kill|terminate|stop|drain)\b.*pid\s*(\d+)", "kill_pid"),
    (r"\b(kill|terminate|stop|drain)\b.*port\s*(\d+)", "drain_port"),
    (r"\b(close socket|force release)\b", "force_release")
]


def classify_intent_deterministic(query: str) -> RoutingDecision:
    """
    Sub-10ms Regex & Heuristic Classifier.
    Eliminates cold-start LLM latency for standard developer commands.
    """
    q_norm = query.lower().strip()

    # Step 1: Intercept destructive operations
    for pattern, intent in DESTRUCTIVE_PATTERNS:
        match = re.search(pattern, q_norm)
        if match:
            target_num = int(match.group(2)) if match.lastindex and match.lastindex >= 2 else None
            pid = target_num if "pid" in intent else None
            port = target_num if "port" in intent else None
            return RoutingDecision(
                route="destructive_action",
                intent_category=intent,
                confidence=0.98,
                requires_2pc_confirm=True,
                target_pid=pid,
                target_port=port,
                execution_plan=f"Pause for explicit 2PC developer confirmation to execute {intent}.",
                raw_query=query
            )

    # Step 2: Intercept rapid status checks
    for pattern, intent in FAST_PATH_PATTERNS:
        if re.search(pattern, q_norm):
            port_match = re.search(r"port\s*(\d+)", q_norm)
            port = int(port_match.group(1)) if port_match else None
            return RoutingDecision(
                route="fast_path",
                intent_category=intent,
                confidence=0.95,
                requires_2pc_confirm=False,
                target_port=port,
                execution_plan="Execute direct procfs socket sensor without Bedrock API overhead.",
                raw_query=query
            )

    # Step 3: Check for deep repository multi-agent audit
    if re.search(r"\b(audit.*repo|aegisagent|run.*audit|stage.*patch|multi-agent|triage.*repo)\b", q_norm):
        return RoutingDecision(
            route="agentic_audit",
            intent_category="deep_code_investigation",
            confidence=0.88,
            requires_2pc_confirm=False,
            execution_plan="Engage multi-agent Bedrock reasoning loop for deep repository inspection.",
            raw_query=query
        )

    # Step 4: General conversational assistance routes to Amazon Nova Pro
    return RoutingDecision(
        route="conversational_bedrock",
        intent_category="conversational_assistance",
        confidence=0.92,
        requires_2pc_confirm=False,
        execution_plan="Engage Amazon Nova Pro conversational intelligence engine.",
        raw_query=query
    )


def execute_fast_path(decision: RoutingDecision) -> FastPathResult:
    """
    Directly queries local sockets, eBPF state, anomalies, or cluster topology in Python.
    Executes in under 10ms, keeping voice interactions snappy and responsive.
    """
    t0 = time.time()
    intent = decision.intent_category
    target_ports = [decision.target_port] if decision.target_port else None

    if intent == "ebpf_trace":
        from src.ebpf_sentry import audit_ebpf_socket_lifecycle
        rep = audit_ebpf_socket_lifecycle(target_ports=target_ports)
        elapsed_ms = round((time.time() - t0) * 1000.0, 2)
        return FastPathResult(
            success=True,
            route="fast_path",
            latency_ms=elapsed_ms,
            speech_text=f"eBPF Kernel Audit: Scanned {rep.total_sockets_scanned} sockets across 11 TCP states. Verdict: {rep.health_verdict}",
            data=rep.model_dump()
        )

    elif intent == "anomaly_prediction":
        from src.anomaly_engine import evaluate_system_anomalies
        anom_rep = evaluate_system_anomalies()
        elapsed_ms = round((time.time() - t0) * 1000.0, 2)
        return FastPathResult(
            success=True,
            route="fast_path",
            latency_ms=elapsed_ms,
            speech_text=anom_rep.voice_summary,
            data=anom_rep.model_dump()
        )

    elif intent == "cluster_fleet":
        from src.cluster_manager import DistributedFleetManager
        raw_q = decision.raw_query.lower()
        if "staging" in raw_q:
            topo = DistributedFleetManager.get_cluster_topology("staging-ecs")
            speech = f"Staging ECS cluster topology: {len(topo.nodes)} tasks active. Socket saturation at {topo.socket_saturation_pct}%."
            data = topo.model_dump()
        elif "prod" in raw_q or "k8s" in raw_q:
            topo = DistributedFleetManager.get_cluster_topology("production-k8s")
            speech = f"Production Kubernetes cluster: {len(topo.nodes)} worker nodes. Ingress saturation at {topo.socket_saturation_pct}%."
            data = topo.model_dump()
        else:
            fleet = DistributedFleetManager.audit_entire_fleet()
            speech = fleet.spoken_summary
            data = fleet.model_dump()

        elapsed_ms = round((time.time() - t0) * 1000.0, 2)
        return FastPathResult(
            success=True,
            route="fast_path",
            latency_ms=elapsed_ms,
            speech_text=speech,
            data=data
        )

    elif intent == "bedrock_mesh":
        from src.bedrock_mesh import BedrockResiliencyMesh
        mesh = BedrockResiliencyMesh()
        mesh_res = mesh.dispatch_inference(decision.raw_query)
        elapsed_ms = round((time.time() - t0) * 1000.0, 2)
        return FastPathResult(
            success=True,
            route="fast_path",
            latency_ms=elapsed_ms,
            speech_text=f"Bedrock Mesh routed to {mesh_res.active_model_id} in {mesh_res.latency_ms} ms. Status: {mesh_res.status}.",
            data=mesh_res.model_dump()
        )

    else:
        # Default socket sentry
        report = audit_local_sockets(target_ports=target_ports)
        elapsed_ms = round((time.time() - t0) * 1000.0, 2)

        # Format natural Alexa speech text
        if report.zombies_detected > 0:
            speech = f"Alert: Found {report.zombies_detected} zombie process holding inspected ports."
        elif report.active_listeners > 0:
            speech = f"Sentinel status: {report.active_listeners} listening services active across monitored ports. Zero zombies detected."
        else:
            speech = "All monitored ports are clean and ready for binding."

        return FastPathResult(
            success=True,
            route="fast_path",
            latency_ms=elapsed_ms,
            speech_text=speech,
            data=report.model_dump()
        )


def route_and_execute(query: str, confirm_destructive: bool = False) -> Dict[str, Any]:
    """
    Main dispatching gateway for Alexa voice utterances and web simulator inputs.
    """
    decision = classify_intent_deterministic(query)

    if decision.route == "fast_path":
        fast_res = execute_fast_path(decision)
        return {
            "route": "fast_path",
            "decision": decision.model_dump(),
            "result": fast_res.model_dump()
        }

    elif decision.route == "destructive_action":
        if not confirm_destructive:
            return {
                "route": "destructive_action",
                "status": "CONFIRMATION_REQUIRED",
                "speech_text": f"Safety check: Are you sure you want to terminate PID {decision.target_pid}? Say 'confirm' to proceed.",
                "decision": decision.model_dump(),
                "requires_2pc_confirm": True
            }
        else:
            term_res = terminate_zombie_process(decision.target_pid, confirm=True)
            msg = (
                f"Terminated PID {decision.target_pid} successfully."
                if term_res.get("success") else
                f"Failed to terminate PID {decision.target_pid}: {term_res.get('message', 'unknown error')}"
            )
            return {
                "route": "destructive_action",
                "status": "EXECUTED",
                "speech_text": msg,
                "decision": decision.model_dump(),
                "result": term_res
            }

    elif decision.route == "conversational_bedrock":
        from src.bedrock_mesh import BedrockResiliencyMesh
        mesh = BedrockResiliencyMesh()
        res = mesh.dispatch_conversational(query)
        output_speech = res.payload_response.get("raw_output", "Understood. Infrastructure telemetry normal.")
        return {
            "route": "conversational_bedrock",
            "status": "CONVERSATIONAL_REPLY",
            "speech_text": output_speech,
            "latency_ms": res.latency_ms,
            "model": res.active_model_id,
            "decision": decision.model_dump(),
            "data": res.model_dump()
        }

    else:
        # Multi-agent audit loop
        return {
            "route": "agentic_audit",
            "status": "AGENTIC_LOOP_ENGAGED",
            "speech_text": "Engaging Sentinel multi-agent audit on target repository.",
            "decision": decision.model_dump()
        }
