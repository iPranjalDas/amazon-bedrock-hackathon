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
    (r"\b(diagram|architecture|visual topology|verify diagram)\b", "verify_diagram"),
    (r"\b(pr|pull request|unified diff|git patch)\b", "generate_pr"),
    (r"\b(friction log|shape feedback|amazon rfc)\b", "friction_log"),
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
    (r"\b(kill|terminate|stop|drain)\b.*port\s*(\d+)", "drain_port"),
    (r"\b(release|free|clear)\b.*port\s*(\d+)", "drain_port"),
    (r"\b(kill|terminate|stop|drain)\b(?:\s+(?:process|pid|worker))?\s+(\d+)", "kill_pid"),
    (r"\b(close socket|force release)\b", "force_release")
]

# Multi-Turn Anaphoric and Confirmation Patterns (Art Museum / Province Standard)
ANAPHORIC_KILL_PATTERNS = [
    r"\b(kill|terminate|stop|drain)\s+(it|this|that|process|worker|service)\b",
    r"\b(kill|terminate|stop|drain)\s+the\s+(zombie|process|port|listener)\b",
    r"\b(free|release|clear)\s+(it|this|that)\b"
]

AFFIRMATIVE_CONFIRM_PATTERNS = [
    r"^(yes|confirm|proceed|do it|execute|go ahead|terminate it|kill it)\b",
    r"\b(yes please|i confirm|confirmed)\b"
]

import threading
from collections import OrderedDict

class ConversationalSessionState:
    """Retains ephemeral conversational context across sequential developer utterances."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.last_queried_port: Optional[int] = None
        self.last_detected_pid: Optional[int] = None
        self.last_intent: Optional[str] = None
        self.confirmation_pending: bool = False
        self.staged_incident_id: Optional[str] = None
        self.last_touch_timestamp: float = time.time()

    def update_touch(self):
        self.last_touch_timestamp = time.time()

    def model_dump(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "last_queried_port": self.last_queried_port,
            "last_detected_pid": self.last_detected_pid,
            "last_intent": self.last_intent,
            "confirmation_pending": self.confirmation_pending,
            "staged_incident_id": self.staged_incident_id,
            "last_touch_timestamp": self.last_touch_timestamp
        }


class SessionManager:
    """Thread-safe conversational session manager with LRU capacity (max 100) and 300s TTL."""
    def __init__(self, max_sessions: int = 100, ttl_seconds: float = 300.0):
        self._sessions: OrderedDict[str, ConversationalSessionState] = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_sessions
        self._ttl = ttl_seconds

    def get_or_create(self, session_id: str = "default-dev") -> ConversationalSessionState:
        # Sanitize session_id to prevent injection
        clean_sid = re.sub(r"[^a-zA-Z0-9_\-]", "", str(session_id))[:64] or "default-dev"
        with self._lock:
            self._prune_expired()
            if clean_sid in self._sessions:
                session = self._sessions[clean_sid]
                self._sessions.move_to_end(clean_sid)
                session.update_touch()
                return session
            if len(self._sessions) >= self._max:
                self._sessions.popitem(last=False)
            session = ConversationalSessionState(clean_sid)
            self._sessions[clean_sid] = session
            return session

    def _prune_expired(self):
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_touch_timestamp > self._ttl]
        for sid in expired:
            del self._sessions[sid]


_GLOBAL_SESSIONS = SessionManager(max_sessions=100, ttl_seconds=300.0)


def classify_intent_deterministic(query: str, session: Optional[ConversationalSessionState] = None) -> RoutingDecision:
    """
    Sub-10ms Regex & Heuristic Classifier with Slot Carryover.
    Eliminates cold-start LLM latency for standard developer commands.
    """
    q_norm = query.lower().strip()

    # Step 0: Check for 2PC Affirmative Confirmation on carried-over target
    if session and session.confirmation_pending and (session.last_detected_pid or session.last_queried_port):
        if any(re.search(pat, q_norm) for pat in AFFIRMATIVE_CONFIRM_PATTERNS):
            return RoutingDecision(
                route="destructive_action",
                intent_category="confirmed_kill_slot",
                confidence=0.99,
                requires_2pc_confirm=False,
                target_pid=session.last_detected_pid,
                target_port=session.last_queried_port,
                execution_plan=f"Execute confirmed 2PC termination on carried-over target (PID {session.last_detected_pid} / Port {session.last_queried_port}).",
                raw_query=query
            )

    # Step 1: Check for Anaphoric Kill/Drain using Slot Carryover ("kill it", "drain it")
    if session and (session.last_queried_port or session.last_detected_pid):
        for pattern in ANAPHORIC_KILL_PATTERNS:
            if re.search(pattern, q_norm):
                session.confirmation_pending = True
                return RoutingDecision(
                    route="destructive_action",
                    intent_category="drain_carried_over_slot",
                    confidence=0.96,
                    requires_2pc_confirm=True,
                    target_pid=session.last_detected_pid,
                    target_port=session.last_queried_port,
                    execution_plan=f"Pause for 2PC confirmation to terminate carried-over target (Port {session.last_queried_port} / PID {session.last_detected_pid}).",
                    raw_query=query
                )

    # Step 2: Intercept explicit destructive operations
    for pattern, intent in DESTRUCTIVE_PATTERNS:
        match = re.search(pattern, q_norm)
        if match:
            target_num = int(match.group(2)) if match.lastindex and match.lastindex >= 2 else None
            pid = target_num if "pid" in intent else None
            port = target_num if "port" in intent else None
            if session:
                if port: session.last_queried_port = port
                if pid: session.last_detected_pid = pid
                session.confirmation_pending = True
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

    # Step 3: Intercept rapid status checks (updates session.last_queried_port)
    for pattern, intent in FAST_PATH_PATTERNS:
        if re.search(pattern, q_norm):
            port_match = re.search(r"port\s*(\d+)", q_norm)
            port = int(port_match.group(1)) if port_match else None
            if session and port:
                session.last_queried_port = port
                session.confirmation_pending = False
            return RoutingDecision(
                route="fast_path",
                intent_category=intent,
                confidence=0.95,
                requires_2pc_confirm=False,
                target_port=port,
                execution_plan="Execute direct procfs socket sensor without Bedrock API overhead.",
                raw_query=query
            )

    # Step 4: Check for deep repository multi-agent audit
    if re.search(r"\b(audit.*repo|aegisagent|run.*audit|stage.*patch|multi-agent|triage.*repo)\b", q_norm):
        return RoutingDecision(
            route="agentic_audit",
            intent_category="deep_code_investigation",
            confidence=0.88,
            requires_2pc_confirm=False,
            execution_plan="Engage multi-agent Bedrock reasoning loop for deep repository inspection.",
            raw_query=query
        )

    # Step 5: General conversational assistance routes to Amazon Nova Pro
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

    elif intent == "verify_diagram":
        from src.vision_verifier import ArchitectureVisionVerifier
        verifier = ArchitectureVisionVerifier()
        rep = verifier.verify_diagram()
        elapsed_ms = round((time.time() - t0) * 1000.0, 2)
        return FastPathResult(
            success=True,
            route="fast_path",
            latency_ms=elapsed_ms,
            speech_text=f"Architecture verification complete. {rep.declared_services_count} declared services audited against kernel sockets. Drift score: {rep.drift_score}. Status: {rep.status}.",
            data=rep.model_dump()
        )

    elif intent == "generate_pr":
        from src.remediation_engine import DynamicRemediationEngine
        target_port = decision.target_port or 3000
        pr = DynamicRemediationEngine.generate_socket_drain_patch("server.py", port=target_port)
        elapsed_ms = round((time.time() - t0) * 1000.0, 2)
        return FastPathResult(
            success=True,
            route="fast_path",
            latency_ms=elapsed_ms,
            speech_text=f"Synthesized atomic unified diff for port {target_port}. AST syntax validated. Branch staged: {pr.branch_name}.",
            data=pr.model_dump()
        )

    elif intent == "friction_log":
        from src.agent_hierarchy import SentinelOrchestrator
        orch = SentinelOrchestrator()
        friction = orch._build_friction_log()
        elapsed_ms = round((time.time() - t0) * 1000.0, 2)
        return FastPathResult(
            success=True,
            route="fast_path",
            latency_ms=elapsed_ms,
            speech_text=f"Amazon Developer Friction Log: Reported {friction.task}. Severity: {friction.severity}. Suggestion: {friction.actionable_suggestion[:100]}...",
            data=friction.model_dump()
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


def route_and_execute(query: str, confirm_destructive: bool = False, session_id: str = "default-dev") -> Dict[str, Any]:
    """
    Main dispatching gateway for Alexa voice utterances and web simulator inputs.
    Features Multi-Turn Slot Carryover & 2PC Affirmative Confirmation (Art Museum / Province Standard).
    """
    session = _GLOBAL_SESSIONS.get_or_create(session_id)
    decision = classify_intent_deterministic(query, session=session)
    session.last_intent = decision.intent_category

    if decision.route == "fast_path":
        fast_res = execute_fast_path(decision)

        # Hydrate session with detected active PID / Port
        if fast_res.data and isinstance(fast_res.data, dict) and "findings" in fast_res.data:
            for f in fast_res.data.get("findings", []):
                pid_val = f.get("pid") if isinstance(f, dict) else getattr(f, "pid", None)
                port_val = f.get("port") if isinstance(f, dict) else getattr(f, "port", None)
                if pid_val and pid_val > 1:
                    session.last_detected_pid = pid_val
                    if port_val: session.last_queried_port = port_val
                    break

        return {
            "route": "fast_path",
            "decision": decision.model_dump(),
            "result": fast_res.model_dump(),
            "session_state": session.model_dump()
        }

    elif decision.route == "destructive_action":
        target_pid = decision.target_pid or session.last_detected_pid
        target_port = decision.target_port or session.last_queried_port

        if target_pid is None and target_port is not None:
            # Dynamically resolve PID holding target_port
            from src.socket_sentry import audit_local_sockets
            report = audit_local_sockets(target_ports=[target_port])
            for f in report.findings:
                if f.port == target_port and f.pid and f.pid > 1:
                    target_pid = f.pid
                    session.last_detected_pid = f.pid
                    break

        is_already_confirmed = confirm_destructive or (decision.intent_category == "confirmed_kill_slot")

        if not is_already_confirmed:
            session.confirmation_pending = True
            if target_pid: session.last_detected_pid = target_pid
            if target_port: session.last_queried_port = target_port

            prompt_target = f"PID {target_pid}" if target_pid else f"service on port {target_port}"
            return {
                "route": "destructive_action",
                "status": "CONFIRMATION_REQUIRED",
                "speech_text": f"Safety check: Are you sure you want to terminate {prompt_target}? Say 'confirm' to proceed.",
                "decision": decision.model_dump(),
                "requires_2pc_confirm": True,
                "resolved_pid": target_pid,
                "session_state": session.model_dump()
            }
        else:
            session.confirmation_pending = False
            if target_pid is None or target_pid <= 1:
                return {
                    "route": "destructive_action",
                    "status": "ERROR",
                    "speech_text": f"Cannot terminate: No active process PID found on port {target_port or 'specified'}.",
                    "decision": decision.model_dump(),
                    "result": {"success": False, "message": "No PID found"},
                    "session_state": session.model_dump()
                }
            term_res = terminate_zombie_process(target_pid, confirm=True)
            msg = (
                f"Terminated PID {target_pid} successfully."
                if term_res.get("success") else
                f"Failed to terminate PID {target_pid}: {term_res.get('message', 'unknown error')}"
            )
            # Reset session after successful execution
            session.last_detected_pid = None
            return {
                "route": "destructive_action",
                "status": "EXECUTED",
                "speech_text": msg,
                "decision": decision.model_dump(),
                "result": term_res,
                "session_state": session.model_dump()
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
            "data": res.model_dump(),
            "session_state": session.model_dump()
        }

    else:
        # Multi-agent audit loop
        return {
            "route": "agentic_audit",
            "status": "AGENTIC_LOOP_ENGAGED",
            "speech_text": "Engaging Sentinel multi-agent audit on target repository.",
            "decision": decision.model_dump(),
            "session_state": session.model_dump()
        }
