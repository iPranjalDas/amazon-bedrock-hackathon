# //Pranjal Das
"""
Unit tests for Sentinel+ Autonomous Remediation Engine.
Validates unified diff generation, AST syntax validation, and 2PC pull request packaging.
"""
import ast
import pytest
from src.remediation_engine import DynamicRemediationEngine, GitHubPullRequestEnvelope


def test_remediation_engine_generates_valid_patch():
    envelope = DynamicRemediationEngine.generate_socket_drain_patch("test_server.py", port=3000)

    assert envelope.branch_name.startswith("sentinel/patch-socket-leak-3000-")
    assert "port 3000" in envelope.pr_title
    assert "CWE-404" in envelope.cwe_id
    assert envelope.syntax_validated is True
    assert envelope.safety_score > 0.90
    assert envelope.requires_2pc is True
    assert "@@ -" in envelope.unified_diff
    assert "+def _sentinel_sigterm_drain" in envelope.unified_diff


def test_remediation_engine_ast_compilation_integrity():
    envelope = DynamicRemediationEngine.generate_socket_drain_patch("server.py", port=8080)
    # Validate that injected signal snippet itself is 100% valid Python AST
    parsed = ast.parse(DynamicRemediationEngine.GRACEFUL_SHUTDOWN_SNIPPET)
    assert parsed is not None
