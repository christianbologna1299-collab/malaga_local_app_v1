"""
Banker Analytics Policy Enforcement Module

Integrates POLICY.md rules into app.py as runtime validators and decorators.
Enforces: user isolation, ownership checks, determinism, safe-fail, auditability.
"""

import logging
import functools
import uuid
from datetime import datetime
from typing import Callable, Any, Optional, Dict
from fastapi import HTTPException, status
from starlette.requests import Request

logger = logging.getLogger(__name__)

# =============================================================================
# POLICY CONFIGURATION (From POLICY.md)
# =============================================================================

POLICY = {
    "priority": "correctness > auditability > reliability > speed > new features",
    "core_principles": [
        "Deterministic-first: Same inputs → same outputs",
        "Single Source of Truth: No duplicate business logic",
        "Hard user isolation: user_id boundary enforced everywhere",
        "Safe-fail by design: Failures degrade gracefully; no silent corruption",
        "Auditability: Every artifact is defendable (what data, when, how, which version)",
        "Local-first: Works on Windows, no Docker, no cloud dependency",
    ],
    "architecture": {
        "routes": "auth checks + input parsing + response rendering only",
        "services": "orchestration (load, compute, store)",
        "domain": "pure deterministic computations",
        "db_layer": "CRUD only (no business logic)",
        "templates": "presentation only (no calculations beyond formatting)",
    },
    "ownership_checks_required": [
        "analysis_id",
        "scenario_id",
        "export_id",
        "stored files",
    ],
    "safe_fail_examples": [
        "Trend compute fails → analysis still saved; trends marked unavailable",
        "PDF export fails → scenario may still exist; export record not created",
        "Cleanup never deletes referenced exports",
    ],
}

# =============================================================================
# REQUEST LOGGING & TRACEABILITY (Policy #9: Logging & Traceability)
# =============================================================================

class RequestContext:
    """Encapsulates per-request tracing data (Policy #9)."""

    def __init__(self):
        self.request_id = str(uuid.uuid4())[:8]
        self.route_name: Optional[str] = None
        self.user_id: Optional[int] = None
        self.analysis_id: Optional[int] = None
        self.scenario_id: Optional[int] = None
        self.export_id: Optional[int] = None
        self.start_time = datetime.now()
        self.errors: list = []

    def duration_ms(self) -> float:
        """Get request duration in milliseconds."""
        return (datetime.now() - self.start_time).total_seconds() * 1000

    def log_context(self) -> Dict[str, Any]:
        """Return dict for structured logging."""
        return {
            "request_id": self.request_id,
            "route": self.route_name,
            "user_id": self.user_id,
            "analysis_id": self.analysis_id,
            "scenario_id": self.scenario_id,
            "export_id": self.export_id,
            "duration_ms": round(self.duration_ms(), 2),
            "errors": self.errors,
        }


# Global context storage (for current request)
_request_context: Optional[RequestContext] = None


def get_request_context() -> RequestContext:
    """Get or create request context for current request."""
    global _request_context
    if _request_context is None:
        _request_context = RequestContext()
    return _request_context


def reset_request_context():
    """Reset context after request completes."""
    global _request_context
    _request_context = None


# =============================================================================
# OWNERSHIP VERIFICATION (Policy #4: Security - Hard Isolation)
# =============================================================================

def verify_user_owns_analysis(
    request: Request,
    analysis_id: int,
    db: Any,
    route_name: str = ""
) -> int:
    """
    Verify current user owns analysis_id.

    Policy #4: "No ownership check, no merge."

    Args:
        request: Starlette request
        analysis_id: Analysis ID to verify
        db: Database instance
        route_name: Route name for logging

    Returns:
        user_id if verified

    Raises:
        HTTPException(404) if not owned
    """
    from core.auth import get_current_user

    current_user = get_current_user(request)
    if not current_user:
        ctx = get_request_context()
        ctx.errors.append("User not authenticated")
        logger.warning(
            "POLICY VIOLATION: Access to analysis without auth",
            extra=ctx.log_context()
        )
        raise HTTPException(status_code=status.HTTP_302_FOUND, detail="Redirect to login")

    user_id = current_user["user_id"]
    analysis = db.get_analysis(analysis_id, user_id)

    if not analysis:
        ctx = get_request_context()
        ctx.user_id = user_id
        ctx.analysis_id = analysis_id
        ctx.route_name = route_name
        ctx.errors.append(f"User {user_id} does not own analysis {analysis_id}")

        logger.warning(
            "POLICY VIOLATION: Cross-user analysis access denied",
            extra=ctx.log_context()
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found or access denied"
        )

    ctx = get_request_context()
    ctx.user_id = user_id
    ctx.analysis_id = analysis_id
    ctx.route_name = route_name

    return user_id


def verify_user_owns_scenario(
    request: Request,
    scenario_id: int,
    db: Any,
    route_name: str = ""
) -> int:
    """
    Verify current user owns scenario_id.

    Policy #4: "No ownership check, no merge."

    Args:
        request: Starlette request
        scenario_id: Scenario ID to verify
        db: Database instance
        route_name: Route name for logging

    Returns:
        user_id if verified

    Raises:
        HTTPException(403) if not owned
    """
    from core.auth import get_current_user

    current_user = get_current_user(request)
    if not current_user:
        ctx = get_request_context()
        ctx.errors.append("User not authenticated")
        logger.warning(
            "POLICY VIOLATION: Access to scenario without auth",
            extra=ctx.log_context()
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authenticated")

    user_id = current_user["user_id"]
    scenario = db.execute_query(
        "SELECT user_id FROM scenarios WHERE id = ?",
        (scenario_id,),
        fetch="one"
    )

    if not scenario or scenario["user_id"] != user_id:
        ctx = get_request_context()
        ctx.user_id = user_id
        ctx.scenario_id = scenario_id
        ctx.route_name = route_name
        ctx.errors.append(f"User {user_id} does not own scenario {scenario_id}")

        logger.warning(
            "POLICY VIOLATION: Cross-user scenario access denied",
            extra=ctx.log_context()
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scenario not found or access denied"
        )

    ctx = get_request_context()
    ctx.user_id = user_id
    ctx.scenario_id = scenario_id
    ctx.route_name = route_name

    return user_id


# =============================================================================
# DECORATORS FOR ROUTE ENFORCEMENT
# =============================================================================

def policy_audit(route_name: str):
    """
    Decorator: Enable audit logging for route (Policy #9: Logging & Traceability).

    Usage:
        @app.get("/snapshot/a/{analysis_id}")
        @policy_audit("snapshot_analysis")
        async def snapshot_analysis(...):
            ...

    Logs:
        - request_id (unique per request)
        - route name
        - user_id
        - analysis_id (if applicable)
        - duration
        - errors
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            ctx = get_request_context()
            ctx.route_name = route_name

            try:
                result = await func(*args, **kwargs)

                logger.info(
                    f"✓ Route {route_name} completed successfully",
                    extra=ctx.log_context()
                )
                reset_request_context()
                return result

            except HTTPException as e:
                ctx.errors.append(str(e.detail))
                logger.warning(
                    f"⚠ Route {route_name} returned HTTP {e.status_code}",
                    extra=ctx.log_context()
                )
                reset_request_context()
                raise

            except Exception as e:
                ctx.errors.append(str(e))
                logger.error(
                    f"✗ Route {route_name} failed with exception",
                    extra=ctx.log_context(),
                    exc_info=True
                )
                reset_request_context()
                raise

        return wrapper

    return decorator


def policy_safe_fail(operation_name: str):
    """
    Decorator: Ensure operation fails safely (doesn't corrupt state).

    Policy #6: Safe-Fail & Containment.

    Usage:
        @policy_safe_fail("trend_computation")
        def compute_trends(...):
            ...

    Behavior:
        - Logs all errors with context
        - Does not re-raise (caller decides if fatal)
        - Returns None on failure
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            ctx = get_request_context()

            try:
                result = func(*args, **kwargs)
                logger.debug(f"✓ Operation {operation_name} succeeded")
                return result

            except Exception as e:
                ctx.errors.append(f"{operation_name}: {str(e)}")
                logger.warning(
                    f"⚠ Operation {operation_name} failed (non-fatal)",
                    extra=ctx.log_context(),
                    exc_info=False
                )
                return None

        return wrapper

    return decorator


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

def validate_filename(filename: str) -> str:
    """
    Validate filename against path traversal attacks.

    Policy #5: Data Handling Rules.

    Args:
        filename: User-supplied filename

    Returns:
        Sanitized filename

    Raises:
        ValueError if invalid
    """
    if not filename or len(filename) == 0:
        raise ValueError("Filename cannot be empty")

    if ".." in filename or "/" in filename or "\\" in filename:
        logger.warning(f"POLICY VIOLATION: Path traversal attempt in filename: {filename}")
        raise ValueError("Invalid filename: contains path traversal characters")

    # Remove leading/trailing whitespace
    return filename.strip()


def validate_determinism_contract(
    analysis_id: int,
    engine_version: str,
    inputs_hash: str,
    computed_at: datetime
) -> bool:
    """
    Validate determinism contract (Policy #3).

    Args:
        analysis_id: Analysis being computed
        engine_version: Version string (e.g., "v1.0")
        inputs_hash: SHA256 of inputs
        computed_at: Timestamp when computed

    Returns:
        True if valid

    Raises:
        ValueError if contract violated
    """
    if not engine_version:
        raise ValueError("engine_version required for determinism contract")

    if not inputs_hash:
        raise ValueError("inputs_hash required for determinism contract")

    if not computed_at:
        raise ValueError("computed_at required for determinism contract")

    # Log for auditability
    logger.debug(
        f"Determinism contract: analysis={analysis_id}, "
        f"version={engine_version}, "
        f"inputs_hash={inputs_hash}, "
        f"computed_at={computed_at}"
    )

    return True


# =============================================================================
# POLICY AUDIT TRAIL
# =============================================================================

def log_artifact_metadata(
    artifact_id: int,
    artifact_type: str,  # 'pdf', 'excel', 'trend', 'scenario'
    user_id: int,
    analysis_id: Optional[int] = None,
    template_version: Optional[str] = None,
    file_hash: Optional[str] = None,
) -> None:
    """
    Log artifact metadata for bank-grade auditability.

    Policy #11: Artifact Metadata (Bank Trust).

    Args:
        artifact_id: ID of artifact
        artifact_type: Type of artifact
        user_id: User who created it
        analysis_id: Related analysis (if applicable)
        template_version: Version of template used
        file_hash: SHA256 of artifact
    """
    logger.info(
        f"ARTIFACT CREATED: {artifact_type}",
        extra={
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "user_id": user_id,
            "analysis_id": analysis_id,
            "template_version": template_version,
            "file_hash": file_hash,
            "created_at": datetime.now().isoformat(),
        }
    )


def log_policy_violation(
    violation_type: str,
    user_id: Optional[int] = None,
    analysis_id: Optional[int] = None,
    detail: str = "",
) -> None:
    """
    Log policy violations for security/compliance review.

    Args:
        violation_type: Type of violation (e.g., "cross_user_access", "path_traversal")
        user_id: User involved
        analysis_id: Analysis involved (if applicable)
        detail: Additional detail
    """
    logger.error(
        f"POLICY VIOLATION DETECTED: {violation_type}",
        extra={
            "violation_type": violation_type,
            "user_id": user_id,
            "analysis_id": analysis_id,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        }
    )


# =============================================================================
# POLICY SUMMARY & COMPLIANCE REPORT
# =============================================================================

def print_policy_summary() -> None:
    """Print policy summary to console."""
    print("\n" + "="*70)
    print("BANKER ANALYTICS — ENGINEERING POLICY ENFORCEMENT")
    print("="*70)
    print(f"\nPriority: {POLICY['priority']}\n")

    print("Core Principles:")
    for principle in POLICY['core_principles']:
        print(f"  ✓ {principle}")

    print("\nArchitecture Layers:")
    for layer, desc in POLICY['architecture'].items():
        print(f"  • {layer}: {desc}")

    print("\nOwnership Checks Required For:")
    for item in POLICY['ownership_checks_required']:
        print(f"  • {item}")

    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    print_policy_summary()
