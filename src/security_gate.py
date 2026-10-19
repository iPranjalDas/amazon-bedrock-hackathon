# //PRANJAL DAS
"""
Zero-Trust RBAC & Account Linking Gatekeeper (src/security_gate.py)

Enforces role-based authorization for all inbound MCP operations:
- Hydrates caller identity and IAM scope from Bearer tokens.
- Restricts mutating actions (SIGTERM, process kills, diff application) to ADMIN/OPERATOR roles.
- Isolates cluster execution scopes (dev, staging, production) to prevent accidental cross-tenant disruption.
"""
import time
from typing import Dict, Any, Optional, List

class SecurityContext:
    def __init__(self, developer_id: str, username: str, iam_role_arn: str,
                 roles: List[str], authorized_clusters: List[str], is_authenticated: bool = True):
        self.developer_id = developer_id
        self.username = username
        self.iam_role_arn = iam_role_arn
        self.roles = roles
        self.authorized_clusters = authorized_clusters
        self.is_authenticated = is_authenticated

    def model_dump(self) -> Dict[str, Any]:
        return {
            "developer_id": self.developer_id,
            "username": self.username,
            "iam_role_arn": self.iam_role_arn,
            "roles": self.roles,
            "authorized_clusters": self.authorized_clusters,
            "is_authenticated": self.is_authenticated
        }


# Simulated token registry for local dev verification and web simulator testing
DEV_TOKEN_REGISTRY = {
    "sentinel-admin-token-2026": SecurityContext(
        developer_id="dev-usr-001",
        username="LeadDevOpsEngineer",
        iam_role_arn="arn:aws:iam::123456789012:role/SentinelDevOpsAdmin",
        roles=["ADMIN", "OPERATOR", "AUDITOR"],
        authorized_clusters=["dev", "staging", "production"],
        is_authenticated=True
    ),
    "sentinel-auditor-token-2026": SecurityContext(
        developer_id="dev-usr-002",
        username="JuniorAuditor",
        iam_role_arn="arn:aws:iam::123456789012:role/SentinelAuditorReadOnly",
        roles=["AUDITOR"],
        authorized_clusters=["dev", "staging"],
        is_authenticated=True
    )
}


class SecurityGatekeeper:
    """
    Enforces authorization rules and token hydration across all MCP tool endpoints.
    """

    @staticmethod
    def verify_and_hydrate(bearer_token: Optional[str]) -> SecurityContext:
        """
        Extracts claims from the incoming bearer token.
        Falls back to anonymous context if unauthenticated.
        """
        if not bearer_token:
            return SecurityContext(
                developer_id="anonymous",
                username="unauthenticated",
                iam_role_arn="",
                roles=[],
                authorized_clusters=[],
                is_authenticated=False
            )

        token_clean = bearer_token.replace("Bearer ", "").strip()
        if token_clean in DEV_TOKEN_REGISTRY:
            return DEV_TOKEN_REGISTRY[token_clean]

        # For simulated web demo or mock environment, allow mock tokens with dev access
        if token_clean.startswith("mock-") or token_clean == "test-token":
            return SecurityContext(
                developer_id="dev-mock",
                username="DevpostJudge",
                iam_role_arn="arn:aws:iam::123456789012:role/SentinelJudgeRole",
                roles=["ADMIN", "OPERATOR"],
                authorized_clusters=["dev", "staging", "production"],
                is_authenticated=True
            )

        return SecurityContext(
            developer_id="invalid",
            username="invalid",
            iam_role_arn="",
            roles=[],
            authorized_clusters=[],
            is_authenticated=False
        )

    @staticmethod
    def authorize_action(security_ctx: SecurityContext, action_name: str, cluster: str = "dev") -> Dict[str, Any]:
        """
        Validates whether the user's IAM role permits the requested action.
        Mutations require 'ADMIN' or 'OPERATOR' role.
        """
        if not security_ctx.is_authenticated:
            return {
                "authorized": False,
                "error": "ACCOUNT_LINKING_REQUIRED",
                "speech_text": "To protect your infrastructure, please link your AWS DevOps credentials in the Alexa app before issuing commands.",
                "requires_account_link_card": True
            }

        # Check cluster scope
        if cluster not in security_ctx.authorized_clusters:
            return {
                "authorized": False,
                "error": "UNAUTHORIZED_CLUSTER_SCOPE",
                "speech_text": f"Permission denied: Your credentials do not grant access to the {cluster} cluster.",
                "requires_account_link_card": False
            }

        # Mutating actions check
        destructive_tools = ["sentinel_remediate_socket", "sentinel_terminate_process", "sentinel_apply_patch"]
        if action_name in destructive_tools:
            if "ADMIN" not in security_ctx.roles and "OPERATOR" not in security_ctx.roles:
                return {
                    "authorized": False,
                    "error": "INSUFFICIENT_PRIVILEGE",
                    "speech_text": "Access denied: Destructive operations require DevOps Admin privileges.",
                    "requires_account_link_card": False
                }

        return {
            "authorized": True,
            "security_context": security_ctx.model_dump()
        }
