#!/usr/bin/env python3
# //Pranjal Das
"""
Sentinel+ Command-Line Diagnostic & Remediation Interface (src/cli.py)

Provides direct CLI access to:
- Deterministic socket inspections across local dev and container ports.
- Multi-agent triage pipeline execution with unified diff staging.
- Safe two-phase commit (2PC) termination of orphaned processes.
- Developer platform friction logs formatted as structured JSON.
"""
import sys
import json
import argparse
from pathlib import Path

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from src.socket_sentry import audit_local_sockets, terminate_zombie_process
from src.agent_hierarchy import SentinelOrchestrator

def main():
    parser = argparse.ArgumentParser(
        description="Sentinel+ Autonomous Infrastructure Sentry CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python3 -m src.cli --check\n  python3 -m src.cli --audit-repo\n  python3 -m src.cli --kill-pid 8492 --confirm"
    )
    parser.add_argument("--check", action="store_true", help="Perform instant deterministic socket audit")
    parser.add_argument("--chat", action="store_true", help="Launch interactive conversational chat with Sentinel+ (Amazon Bedrock)")
    parser.add_argument("--ports", type=str, default="3000,5173,8000,8080", help="Comma-separated target ports")
    parser.add_argument("--audit-repo", action="store_true", help="Run full AegisAgent/Sai multi-agent audit")
    parser.add_argument("--kill-pid", type=int, help="Target PID to terminate")
    parser.add_argument("--confirm", action="store_true", help="Two-Phase Commit confirmation flag")
    parser.add_argument("--json", action="store_true", help="Output pure structured JSON")
    parser.add_argument("--friction-log", action="store_true", help="Print official Amazon Developer Friction Log RFC")

    args = parser.parse_args()

    # Case 0: Interactive Terminal Chat REPL
    if args.chat:
        from src.router import route_and_execute
        print("=================================================================")
        print("  🎙️  Sentinel+ Interactive Alexa & Bedrock Console (CLI Chat)")
        print("  Author: Pranjal Das //Pranjal Das")
        print("  Engine: Amazon Nova Pro & Model Context Protocol")
        print("  Type 'exit', 'quit', or 'q' to end session.")
        print("=================================================================\n")
        
        while True:
            try:
                user_msg = input("\033[1;36mYou > \033[0m").strip()
                if not user_msg:
                    continue
                if user_msg.lower() in ["exit", "quit", "q"]:
                    print("\n[Sentinel+] Session ended. Sentry standing by.")
                    break

                res = route_and_execute(user_msg)
                route = res.get("route", "unknown")
                speech = res.get("speech_text") or res.get("result", {}).get("speech_text", "")
                latency = res.get("latency_ms") or res.get("result", {}).get("latency_ms", 0.0)
                model = res.get("model", "Amazon Nova Pro")

                print(f"\033[1;33mSentinel+ [{model} | {latency}ms | {route.upper()}]\033[0m")
                print(f"{speech}\n")
            except (KeyboardInterrupt, EOFError):
                print("\n[Sentinel+] Terminating interactive console. Goodbye.")
                break
        sys.exit(0)

    # Case 1: Kill PID with 2PC
    if args.kill_pid:
        res = terminate_zombie_process(pid=args.kill_pid, confirm=args.confirm)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                print(f"[SUCCESS] {res.get('message')}")
            else:
                print(f"[BLOCKED] {res.get('message', res.get('error'))}")
        sys.exit(0 if res.get("success") else 1)

    # Case 2: Friction Log RFC
    if args.friction_log:
        orchestrator = SentinelOrchestrator(repo_path=str(_REPO_ROOT))
        session = orchestrator.run_multi_agent_audit()
        if session.friction_log:
            print(json.dumps(session.friction_log.model_dump(), indent=2))
        sys.exit(0)

    # Case 3: Full Multi-Agent Audit
    if args.audit_repo:
        orchestrator = SentinelOrchestrator(repo_path=str(_REPO_ROOT))
        session = orchestrator.run_multi_agent_audit()
        if args.json:
            print(json.dumps(session.model_dump(), indent=2))
        else:
            print(f"=== Sentinel+ Multi-Agent Audit Session: {session.session_id} ===")
            print(f"Target Repo: {session.repo_path}")
            print(f"Status:      {session.status}")
            print("\n--- Agent Trace Steps ---")
            for t in session.trace_steps:
                print(f"[{t.agent_name}] ({t.role}): {t.observation}")
                print(f"  Reasoning: {t.reasoning}")
                print(f"  Verdict:   {t.verdict} (Confidence: {t.confidence})\n")
            print(f"Critic Verdict: {session.critic_verdict.verdict} (Risk: {session.critic_verdict.risk_score})")
            if session.remediation_patch:
                print(f"\nStaged PR Patch: {session.remediation_patch.pr_title}")
        sys.exit(0)

    # Case 4: Default Socket Audit
    ports = [int(p.strip()) for p in args.ports.split(",") if p.strip().isdigit()]
    report = audit_local_sockets(target_ports=ports)

    if args.json:
        print(json.dumps(report.model_dump(), indent=2))
    else:
        print("=== Sentinel+ Deterministic System Audit ===")
        print(f"Audited Ports: {report.total_ports_scanned}")
        print(f"Active Listeners: {report.active_listeners}")
        print(f"Zombie PIDs: {report.zombies_detected}")
        print(f"Verdict: {report.summary_verdict}")
        if report.findings:
            print("\nFindings:")
            for f in report.findings:
                status_icon = "⚠️" if f.is_stale_zombie else "ℹ️"
                print(f"  {status_icon} Port {f.port}: {f.process_name} (PID {f.pid}) State: {f.state} [{f.risk_level}]")
                print(f"     Details: {f.details}")

    sys.exit(0 if report.zombies_detected == 0 else 1)

if __name__ == "__main__":
    main()
