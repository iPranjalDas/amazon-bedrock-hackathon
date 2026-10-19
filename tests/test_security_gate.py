# //Pranjal Das
"""
Unit Tests for Sentinel+ Zero-Trust Security Gate (Account Linking & RBAC)
"""
import sys
from pathlib import Path

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from src.security_gate import SecurityGatekeeper

def test_unauthenticated_session_intercepted():
    ctx = SecurityGatekeeper.verify_and_hydrate(bearer_token=None)
    assert ctx.is_authenticated is False

    auth = SecurityGatekeeper.authorize_action(ctx, "sentinel_audit_ports")
    assert auth["authorized"] is False
    assert auth["error"] == "ACCOUNT_LINKING_REQUIRED"
    assert auth["requires_account_link_card"] is True

def test_admin_token_authorized_for_mutations():
    ctx = SecurityGatekeeper.verify_and_hydrate("Bearer sentinel-admin-token-2026")
    assert ctx.is_authenticated is True
    assert "ADMIN" in ctx.roles

    # Read-only tool authorized
    auth_read = SecurityGatekeeper.authorize_action(ctx, "sentinel_audit_ports", cluster="dev")
    assert auth_read["authorized"] is True

    # Mutating tool authorized for admin
    auth_mut = SecurityGatekeeper.authorize_action(ctx, "sentinel_remediate_socket", cluster="dev")
    assert auth_mut["authorized"] is True

def test_auditor_token_blocked_from_mutations():
    ctx = SecurityGatekeeper.verify_and_hydrate("Bearer sentinel-auditor-token-2026")
    assert ctx.is_authenticated is True
    assert "ADMIN" not in ctx.roles

    # Read-only tool authorized
    auth_read = SecurityGatekeeper.authorize_action(ctx, "sentinel_audit_ports", cluster="dev")
    assert auth_read["authorized"] is True

    # Mutating tool BLOCKED for read-only auditor
    auth_mut = SecurityGatekeeper.authorize_action(ctx, "sentinel_remediate_socket", cluster="dev")
    assert auth_mut["authorized"] is False
    assert auth_mut["error"] == "INSUFFICIENT_PRIVILEGE"

def test_unauthorized_cluster_scope_blocked():
    ctx = SecurityGatekeeper.verify_and_hydrate("Bearer sentinel-auditor-token-2026")
    # Auditor only has dev, staging
    auth_prod = SecurityGatekeeper.authorize_action(ctx, "sentinel_audit_ports", cluster="production")
    assert auth_prod["authorized"] is False
    assert auth_prod["error"] == "UNAUTHORIZED_CLUSTER_SCOPE"
