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

    # Step 3: Complex multi-step queries route to the multi-agent Bedrock loop
    return RoutingDecision(
        route="agentic_audit",
        intent_category="deep_code_investigation",
        confidence=0.88,
        requires_2pc_confirm=False,
        execution_plan="Engage multi-agent Bedrock reasoning loop for deep repository inspection.",
        raw_query=query
    )


def execute_fast_path(decision: RoutingDecision) -> FastPathResult:
    """
    Directly queries local sockets in Python.
    Executes in under 10ms, keeping voice interactions snappy and responsive.
    """
    t0 = time.time()
    target_ports = [decision.target_port] if decision.target_port else None
    report = audit_local_sockets(target_ports=target_ports)
    elapsed_ms = round((time.time() - t0) * 1000.0, 2)

    # Format natural Alexa speech text
    if report.zombies_detected > 0:
        speech = f"Alert: Found {report.zombies_detected} zombie process holding inspected ports."
    elif report.active_listeners > 0:
        speech = f"Sentinel status: {report.active_listeners} listening services active. Zero zombies detected."
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

    else:
        # Multi-agent audit loop
        return {
            "route": "agentic_audit",
            "status": "AGENTIC_LOOP_ENGAGED",
            "speech_text": "Engaging Sentinel multi-agent audit on target repository.",
            "decision": decision.model_dump()
        }
