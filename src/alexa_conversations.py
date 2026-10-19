"""
Sentinel+ Alexa Conversations Declarative API Engine (src/alexa_conversations.py)
Implements:
1. Art Museum / pet-match Dialog.API.Invoked Protocol
2. Autonomous Context Carry-Over across server clusters
3. Decoupled Declarative Execution returning { apiResponse }
"""
from typing import Dict, Any, Optional
from src.socket_sentry import audit_local_sockets, terminate_zombie_process

class AlexaConversationsSessionContext:
    def __init__(self):
        self.active_cluster: str = "staging"
        self.last_action: Optional[str] = None
        self.last_inspected_port: Optional[int] = None
        self.last_detected_pid: Optional[int] = None

    def update_with_carry_over(self, args: Dict[str, Any]) -> None:
        """Preserves context when user modifies only one attribute."""
        if "cluster" in args and args["cluster"]:
            self.active_cluster = args["cluster"]
        if "action" in args and args["action"]:
            self.last_action = args["action"]
        if "port" in args and args["port"]:
            self.last_inspected_port = int(args["port"])


# In-memory session store
_CONVERSATION_SESSIONS: Dict[str, AlexaConversationsSessionContext] = {}


def get_or_create_session(session_id: str) -> AlexaConversationsSessionContext:
    if session_id not in _CONVERSATION_SESSIONS:
        _CONVERSATION_SESSIONS[session_id] = AlexaConversationsSessionContext()
    return _CONVERSATION_SESSIONS[session_id]


def handle_dialog_api_invoked(request_envelope: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standard Alexa Conversations entrypoint.
    Receives Dialog.API.Invoked envelope and executes target tool API.
    """
    request = request_envelope.get("request", {})
    session_id = request_envelope.get("session", {}).get("sessionId", "simulated-session")
    session_ctx = get_or_create_session(session_id)

    api_request = request.get("apiRequest", {})
    api_name = api_request.get("name", "unknown")
    arguments = api_request.get("arguments", {})

    # Apply context carry-over
    session_ctx.update_with_carry_over(arguments)

    if api_name == "auditClusterInfrastructure":
        target_port = session_ctx.last_inspected_port
        target_ports = [target_port] if target_port else [3000, 5173, 8000, 8080]
        report = audit_local_sockets(target_ports=target_ports)

        return {
            "apiResponse": {
                "status": "SUCCESS",
                "cluster": session_ctx.active_cluster,
                "portsScanned": report.total_ports_scanned,
                "zombiesDetected": report.zombies_detected,
                "summary": report.summary_verdict,
                "contextCarriedOver": True
            }
        }

    elif api_name == "executeRemediation":
        pid_to_kill = arguments.get("pid", session_ctx.last_detected_pid)
        confirm = arguments.get("confirmed", True)

        if not pid_to_kill:
            return {
                "apiResponse": {
                    "status": "ERROR_MISSING_PID",
                    "message": "No target PID specified or carried over in conversational context."
                }
            }

        res = terminate_zombie_process(pid=int(pid_to_kill), confirm=confirm)
        return {
            "apiResponse": {
                "status": "REMEDIATED" if res.get("success") else "FAILED",
                "cluster": session_ctx.active_cluster,
                "affectedPid": pid_to_kill,
                "signalUsed": res.get("signal_used", "NONE"),
                "message": res.get("message", "")
            }
        }

    else:
        return {
            "apiResponse": {
                "status": "UNKNOWN_API",
                "message": f"Unrecognized Dialog.API.Invoked endpoint: {api_name}"
            }
        }
