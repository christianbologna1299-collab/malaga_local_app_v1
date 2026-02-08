"""
Banker Analytics - Milestone 3.75
FastAPI app with M1 (quick analyze), M2 (feature hub), M3 (multi-user auth),
M3.5 (trend engine), and M3.75 (policy-as-code + audit events + middleware).
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import pandas as pd
import plotly.graph_objects as go
import io

# Core & Features imports
from core.database_session_manager import DatabaseSessionManager
from core.validators import parse_csv, validate_schema, clean_data
from core.calculations import compute_kpis, detect_flags
from core.pdf_generator import (
    SnapshotPDFGenerator,
    SimulatorPDFGenerator,
    ExplainPDFGenerator,
)
from core.chart_converter import PlotlyConverter
from core.auth import hash_password, authenticate_user, login_user, logout_user, get_current_user, create_user
from core.db import Database
from features.borrower_snapshot import (
    build_balance_chart,
    build_rate_chart,
    format_kpi_tiles_html,
    generate_kpi_narrative,
)
from features.simulator import (
    run_shocks,
    build_shock_comparison_chart,
    generate_impact_table_html,
)
from features.explain_engine import generate_full_explanation
from core.policy import (
    PolicyViolation,
    policy_guard,
    policy_log_event,
    ensure_audit_events_table,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# FastAPI Setup
app = FastAPI(title="Banker Analytics", version="3.0")
BASE_DIR = Path(__file__).resolve().parent

# M3: Add SessionMiddleware for session cookie management
SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-production-12345678901234567890")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=None)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# M3: Initialize database (handles users, sessions, and future analysis tables)
db = Database(db_path=str(BASE_DIR / "banker_analytics.db"))
logger.info("Database initialized: users, sessions, and analysis tables ready")

# Session Manager (SQLite-backed, 30-min TTL)
session_manager = DatabaseSessionManager(ttl_minutes=30)
logger.info("DatabaseSessionManager initialized")

# Phase 2: Setup exports directory for PDF exports
EXPORTS_DIR = BASE_DIR / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)
logger.info(f"Exports directory: {EXPORTS_DIR}")

# M3: Setup analyses directory for persisted datasets
ANALYSES_DIR = BASE_DIR / "data" / "analyses"
ANALYSES_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"Analyses directory: {ANALYSES_DIR}")

# M3.75: Ensure audit_events table exists (idempotent, non-fatal)
try:
    _audit_conn = db._get_connection()
    ensure_audit_events_table(_audit_conn)
    _audit_conn.close()
except Exception as e:
    logger.warning(f"Audit events table setup failed (non-fatal): {e}")


# =============================================================================
# M3.75 Phase 1: Policy Middleware
# =============================================================================

# Protected persistent route prefixes that require authentication
_PROTECTED_PREFIXES = (
    "/snapshot/a/",
    "/simulator/a/",
    "/explain/a/",
    "/history",
    "/api/analyses/",
)


class PolicyMiddleware(BaseHTTPMiddleware):
    """
    M3.75: Sets request.state.request_id and request.state.current_user,
    enforces auth for protected persistent routes.
    """

    async def dispatch(self, request: Request, call_next):
        # Assign unique request ID for traceability
        request.state.request_id = str(uuid.uuid4())[:12]

        # Resolve current user from cookies (reuse existing auth)
        request.state.current_user = get_current_user(request)

        # Enforce authentication on protected persistent routes
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _PROTECTED_PREFIXES):
            if not request.state.current_user:
                # JSON endpoints → 403; HTML pages → redirect to login
                if path.startswith("/api/"):
                    return JSONResponse(
                        {"detail": "Authentication required"}, status_code=403
                    )
                return RedirectResponse(url="/login", status_code=302)

        response = await call_next(request)
        return response


# Register AFTER SessionMiddleware in code → runs as outer layer
# (cookies are in HTTP headers, always available regardless of middleware order)
app.add_middleware(PolicyMiddleware)


# =============================================================================
# M3.75 Phase 1: Uniform PolicyViolation Exception Handler
# =============================================================================

@app.exception_handler(PolicyViolation)
async def policy_violation_handler(request: Request, exc: PolicyViolation):
    """M3.75: Uniform handler — HTML for pages, JSON for /api/* routes."""
    logger.warning(f"PolicyViolation: [{exc.rule}] {exc.detail}")

    # Audit the violation
    current_user = get_current_user(request)
    user_id = current_user["user_id"] if current_user else None
    policy_log_event(
        db=db,
        user_id=user_id,
        event_kind="policy_violation",
        details_json=json.dumps({"rule": exc.rule, "detail": exc.detail}),
        request_id=getattr(request.state, "request_id", None),
    )

    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"detail": f"Policy violation: {exc.detail}", "rule": exc.rule},
            status_code=403,
        )

    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": f"Policy violation: {exc.detail}"},
        status_code=403,
    )


def cleanup_old_exports(max_age_hours: int = 24):
    """
    Remove PDFs older than max_age_hours, but preserve files referenced in exports table.
    M3: Safety check to prevent deleting referenced exports.
    """
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    deleted = 0
    preserved = 0

    if not EXPORTS_DIR.exists():
        return deleted

    # Get list of files referenced in exports table
    try:
        referenced_paths = set()
        export_records = db.execute_query(
            "SELECT file_path FROM exports",
            fetch="all"
        )
        if export_records:
            for record in export_records:
                # Convert to absolute path for comparison
                file_path = record['file_path']
                if not Path(file_path).is_absolute():
                    file_path = BASE_DIR / file_path
                else:
                    file_path = Path(file_path)
                referenced_paths.add(file_path.resolve())

        logger.info(f"Cleanup: found {len(referenced_paths)} referenced exports in DB")
    except Exception as e:
        logger.warning(f"Failed to query exports table: {e}")
        referenced_paths = set()

    # Delete old PDFs not referenced in DB
    for pdf_file in EXPORTS_DIR.glob("*.pdf"):
        mtime = datetime.fromtimestamp(pdf_file.stat().st_mtime)

        if mtime < cutoff:
            # Check if file is referenced in exports table
            if pdf_file.resolve() in referenced_paths:
                preserved += 1
                logger.debug(f"Cleanup: preserving referenced export {pdf_file.name}")
            else:
                try:
                    pdf_file.unlink()
                    deleted += 1
                    logger.debug(f"Cleanup: deleted orphaned export {pdf_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete {pdf_file}: {e}")

    logger.info(f"Cleanup: deleted {deleted} orphaned PDFs, preserved {preserved} referenced exports")
    return deleted


# Cleanup on startup
cleanup_old_exports()


# ============================================================================
# MILESTONE 3: Authentication Routes (Login, Logout, Register)
# ============================================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display login page."""
    current_user = get_current_user(request)
    if current_user:
        # Already logged in, redirect to hub
        return RedirectResponse(url="/", status_code=302)

    logger.info("GET /login")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Display registration page."""
    current_user = get_current_user(request)
    if current_user:
        # Already logged in, redirect to hub
        return RedirectResponse(url="/", status_code=302)

    logger.info("GET /register")
    return templates.TemplateResponse("login.html", {"request": request, "register_mode": True})


@app.post("/login")
async def login(request: Request, username: str = "", password: str = ""):
    """Handle login form submission."""
    try:
        logger.info(f"POST /login attempt: {username}")

        # For form submissions, parse form data
        if not username or not password:
            form_data = await request.form()
            username = form_data.get("username", "")
            password = form_data.get("password", "")

        if not username or not password:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Username and password are required",
                },
            )

        # Authenticate user
        user_id = authenticate_user(db, username, password)

        if not user_id:
            logger.warning(f"Failed login attempt: {username}")
            # M3.75: Audit login failure
            policy_log_event(
                db=db, user_id=None, event_kind="login_failure",
                details_json=json.dumps({"username": username}),
                request_id=getattr(request.state, "request_id", None),
            )
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Invalid username or password",
                },
            )

        # Create response and set session cookies
        response = RedirectResponse(url="/", status_code=302)
        login_user(response, user_id, username)

        # M3.75: Audit login success
        policy_log_event(
            db=db, user_id=user_id, event_kind="login_success",
            details_json=json.dumps({"username": username}),
            request_id=getattr(request.state, "request_id", None),
        )

        return response

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": f"Login failed: {str(e)}",
            },
        )


@app.post("/logout")
async def logout(request: Request):
    """Handle logout."""
    try:
        current_user = get_current_user(request)
        logger.info(f"POST /logout: {current_user['username'] if current_user else 'unknown'}")

        response = RedirectResponse(url="/login", status_code=302)
        logout_user(response)
        return response

    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return RedirectResponse(url="/login", status_code=302)


@app.post("/register")
async def register(request: Request):
    """Handle user registration."""
    try:
        form_data = await request.form()
        username = form_data.get("username", "").strip()
        password = form_data.get("password", "")
        password_confirm = form_data.get("password_confirm", "")

        logger.info(f"POST /register attempt: {username}")

        # Validation
        if not username or len(username) < 3:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "register_mode": True,
                    "error": "Username must be at least 3 characters",
                },
            )

        if not password or len(password) < 8:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "register_mode": True,
                    "error": "Password must be at least 8 characters",
                },
            )

        if password != password_confirm:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "register_mode": True,
                    "error": "Passwords do not match",
                },
            )

        # Create user
        password_hash = hash_password(password)
        user_id = db.create_user(username, password_hash)

        if not user_id:
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "register_mode": True,
                    "error": "Username already exists",
                },
            )

        logger.info(f"User registered: {username}")

        # M3.75: Audit registration
        policy_log_event(
            db=db, user_id=user_id, event_kind="register",
            details_json=json.dumps({"username": username}),
            request_id=getattr(request.state, "request_id", None),
        )

        # Auto-login after successful registration
        response = RedirectResponse(url="/", status_code=302)
        login_user(response, user_id, username)
        return response

    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "register_mode": True,
                "error": f"Registration failed: {str(e)}",
            },
        )



@app.post("/analyze")
async def analyze(request: Request, file: UploadFile = File(...)):
    """
    Milestone 1: Upload CSV, validate, parse, return report inline.
    Original flow preserved exactly.
    """
    try:
        logger.info(f"M1 /analyze request: {file.filename}")
        contents = await file.read()

        df = parse_csv(contents)
        validate_schema(df)
        df_clean = clean_data(df)

        # Build balance chart
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df_clean["date"],
                y=df_clean["balance"],
                mode="lines+markers",
                name="Balance",
                line=dict(color="#00D9FF", width=2),
                marker=dict(size=6, color="#00D9FF"),
            )
        )
        fig.update_layout(
            title="Balance Over Time",
            xaxis_title="Date",
            yaxis_title="Balance",
            template="plotly_dark",
            height=500,
            hovermode="x unified",
            font=dict(color="#E0E0E0"),
            plot_bgcolor="#1a1a2e",
            paper_bgcolor="#0f0f1e",
            margin=dict(l=60, r=40, t=60, b=60),
        )
        chart_html = fig.to_html(
            include_plotlyjs="cdn", div_id="balance_chart", config={"responsive": True}
        )

        preview = df_clean.head(10).to_html(classes="data-table", index=False)
        stats = (
            df_clean[["balance", "rate"]]
            .describe()
            .round(4)
            .to_html(classes="stats-table")
        )

        return templates.TemplateResponse(
            "report.html",
            {
                "request": request,
                "chart": chart_html,
                "preview": preview,
                "stats": stats,
                "rows_processed": len(df_clean),
            },
        )

    except Exception as e:
        logger.error(f"M1 analyze error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=400
        )


# ============================================================================
# MILESTONE 2: Feature Hub & Session-Based Analytics
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def hub(request: Request):
    """Feature Hub: upload option + M2 feature cards. M3: Auth-aware."""
    logger.info("GET / (hub)")
    current_user = get_current_user(request)
    return templates.TemplateResponse(
        "hub.html",
        {
            "request": request,
            "current_user": current_user,
        },
    )


@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    """
    M2/M3: Upload CSV, validate, parse, store in session.
    If user is logged in, also create persistent analysis record.
    """
    try:
        logger.info(f"POST /upload request: {file.filename}")
        contents = await file.read()

        df = parse_csv(contents)
        validate_schema(df)
        df_clean = clean_data(df)

        # M3.75 Phase 2: Upload gate — policy_guard before storing
        current_user_pre = get_current_user(request)
        nan_fields = [
            col for col in ("date", "balance", "rate")
            if df_clean[col].isna().any()
        ]
        upload_context = {
            "route": "/upload",
            "mode": "persistent" if current_user_pre else "session",
            "filename": file.filename,
            "row_count": len(df_clean),
            "date_min": str(df_clean["date"].min()) if len(df_clean) > 0 else None,
            "date_max": str(df_clean["date"].max()) if len(df_clean) > 0 else None,
            "user_id": current_user_pre["user_id"] if current_user_pre else None,
            "nan_fields": nan_fields,
        }
        policy_guard(upload_context)

        # Always create session for quick mode (backward compat)
        session_id = session_manager.store_session(df_clean, file.filename)
        logger.info(f"Session created: {session_id} for {file.filename}")

        response_data = {
            "session_id": session_id,
            "filename": file.filename,
            "rows": len(df_clean),
        }

        # M3: If user is logged in, create persistent analysis record
        current_user = get_current_user(request)
        if current_user:
            try:
                from core.models import sanitize_filename, compute_file_hash
                import pandas as pd

                # Create analysis record
                safe_filename = sanitize_filename(file.filename)
                date_min = df_clean["date"].min().strftime("%Y-%m-%d") if len(df_clean) > 0 else None
                date_max = df_clean["date"].max().strftime("%Y-%m-%d") if len(df_clean) > 0 else None

                analysis_id = db.create_analysis(
                    user_id=current_user["user_id"],
                    filename=safe_filename,
                    row_count=len(df_clean),
                    date_min=date_min,
                    date_max=date_max,
                )

                if analysis_id:
                    # Save parquet file to disk
                    parquet_path = ANALYSES_DIR / f"{analysis_id}.parquet"
                    df_clean.to_parquet(str(parquet_path), index=False)
                    logger.info(f"Analysis data saved to {parquet_path}")

                    # Compute file hash for integrity
                    file_hash = compute_file_hash(str(parquet_path))

                    # Create analysis_files record
                    file_size = parquet_path.stat().st_size if parquet_path.exists() else None
                    db.create_analysis_file(
                        user_id=current_user["user_id"],
                        analysis_id=analysis_id,
                        stored_path=str(parquet_path.relative_to(BASE_DIR)),
                        file_hash=file_hash,
                        size_bytes=file_size,
                        format="parquet",
                    )

                    # M3.5: Compute trends (Milestone 3.5 - Deterministic Trend Analysis)
                    # Non-fatal: trend computation failure does not block upload success
                    try:
                        from core.trends import compute_trends
                        trends = compute_trends(
                            df=df_clean,
                            date_col="date",
                            balance_col="balance",
                            rate_col="rate",
                            user_id=current_user["user_id"],
                            analysis_id=analysis_id,
                            file_hash=file_hash,
                        )

                        # Store trends in DB (deterministic caching via inputs_hash)
                        for trend in trends:
                            # Check if trend already exists (determinism gate)
                            if not db.trend_exists(trend.inputs_hash):
                                db.create_trend(
                                    user_id=current_user["user_id"],
                                    analysis_id=analysis_id,
                                    window_days=trend.window_days,
                                    series_name=trend.series_name,
                                    metrics_json=trend.to_metrics_json(),
                                    confidence=trend.confidence,
                                    inputs_hash=trend.inputs_hash,
                                    trend_engine_version=trend.trend_engine_version,
                                )

                        logger.info(f"Trends computed and stored: {len(trends)} metrics for analysis {analysis_id}")
                    except Exception as e:
                        logger.warning(f"Trend computation failed (non-fatal): {str(e)}")
                        # M3.75: Audit trend failure (non-fatal, does not block upload)
                        policy_log_event(
                            db=db,
                            user_id=current_user["user_id"],
                            event_kind="trend_compute_failure",
                            details_json=json.dumps({"error": str(e), "analysis_id": analysis_id}),
                            analysis_id=analysis_id,
                            request_id=getattr(request.state, "request_id", None),
                        )

                    response_data["analysis_id"] = analysis_id
                    logger.info(f"Analysis created: {analysis_id} for user {current_user['user_id']}")

            except Exception as e:
                logger.warning(f"Failed to create persistent analysis (continuing with session): {str(e)}")
                # Continue with session-based response if analysis creation fails

        # M3.75: Audit upload event
        policy_log_event(
            db=db,
            user_id=current_user["user_id"] if current_user else None,
            event_kind="upload",
            details_json=json.dumps({
                "filename": file.filename,
                "row_count": len(df_clean),
                "analysis_id": response_data.get("analysis_id"),
            }),
            session_id=session_id,
            request_id=getattr(request.state, "request_id", None),
        )

        return JSONResponse(response_data, status_code=200)

    except PolicyViolation:
        raise  # Let the exception handler deal with it
    except ValueError as e:
        logger.warning(f"Upload validation error: {str(e)}")
        return JSONResponse({"detail": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return JSONResponse({"detail": str(e)}, status_code=500)


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    """
    Display user's analysis history.
    M3: Auth-required. Lists all user's analyses with exports per analysis.
    """
    try:
        logger.info("GET /history")
        current_user = get_current_user(request)

        # Redirect to login if not authenticated
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)

        # Fetch user's analyses (ordered newest first)
        user_id = current_user["user_id"]
        analyses = db.list_user_analyses(user_id, limit=100)

        # Enrich each analysis with its exports and trends
        for analysis in analyses:
            analysis_id = analysis["id"]
            exports = db.list_exports_for_analysis(analysis_id, user_id)
            analysis["exports"] = exports

            # M3.5: Load 90-day trend summary for history badges
            trend_summary = db.list_trend_summary_for_history(user_id, limit=1, window_days=90)
            # Filter to current analysis_id
            analysis_trends = [t for t in trend_summary if t["analysis_id"] == analysis_id]
            if analysis_trends:
                analysis["balance_trend"] = analysis_trends[0].get("balance_trend")
                analysis["rate_trend"] = analysis_trends[0].get("rate_trend")
            else:
                analysis["balance_trend"] = None
                analysis["rate_trend"] = None

            # Format dates for display
            if analysis.get("uploaded_at"):
                try:
                    analysis["uploaded_at_display"] = datetime.strptime(
                        analysis["uploaded_at"], "%Y-%m-%d %H:%M:%S"
                    ).strftime("%B %d, %Y at %I:%M %p")
                except (ValueError, TypeError):
                    analysis["uploaded_at_display"] = analysis.get("uploaded_at", "N/A")

            if analysis.get("date_min"):
                analysis["date_min_display"] = analysis["date_min"]

            if analysis.get("date_max"):
                analysis["date_max_display"] = analysis["date_max"]

        logger.info(f"History loaded: {len(analyses)} analyses for user {user_id}")

        return templates.TemplateResponse(
            "history.html",
            {
                "request": request,
                "current_user": current_user,
                "analyses": analyses,
            },
        )

    except Exception as e:
        logger.error(f"History error: {str(e)}")
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error": f"Failed to load history: {str(e)}",
            },
            status_code=500,
        )


@app.get("/snapshot/{session_id}", response_class=HTMLResponse)
async def snapshot(request: Request, session_id: str):
    """Borrower Snapshot: KPI tiles, charts, flags, narrative."""
    try:
        logger.info(f"GET /snapshot/{session_id}")
        session = session_manager.get_session(session_id)

        if not session:
            logger.warning(f"Session not found or expired: {session_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Session expired. Please upload a new CSV.",
                },
                status_code=404,
            )

        df = session["df"]
        kpis = compute_kpis(df)
        flags = detect_flags(df)

        kpi_html = format_kpi_tiles_html(kpis)

        # Build figures (for both web and PDF)
        balance_fig = build_balance_chart(df)
        rate_fig = build_rate_chart(df)

        # Convert figures to HTML for web display
        balance_chart = balance_fig.to_html(
            include_plotlyjs="cdn", div_id="balance_chart", config={"responsive": True}
        )
        rate_chart = rate_fig.to_html(
            include_plotlyjs=False, div_id="rate_chart", config={"responsive": True}
        )

        narrative = generate_kpi_narrative(kpis, flags)

        has_flags = any(
            [
                flags.get("volatility_spike"),
                flags.get("trend_change"),
                flags.get("missing_dates"),
                flags.get("outlier_count", 0) > 0,
            ]
        )

        logger.info(f"Snapshot rendered for {session_id}")

        return templates.TemplateResponse(
            "snapshot.html",
            {
                "request": request,
                "session_id": session_id,
                "analysis_id": None,  # None for session-based routes
                "route_prefix": "",  # Empty for session-based (/snapshot/{id})
                "route_id": session_id,
                "created_at": session["created_at"].strftime("%Y-%m-%d %H:%M"),
                "kpi_html": kpi_html,
                "balance_chart": balance_chart,
                "rate_chart": rate_chart,
                "flags": flags,
                "has_flags": has_flags,
                "balance_stdev": kpis["balance_stdev"],
                "narrative": narrative,
            },
        )

    except Exception as e:
        logger.error(f"Snapshot error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=500
        )


@app.get("/simulator/{session_id}", response_class=HTMLResponse)
async def simulator_get(request: Request, session_id: str):
    """Simulator GET: show form."""
    try:
        logger.info(f"GET /simulator/{session_id}")
        session = session_manager.get_session(session_id)

        if not session:
            logger.warning(f"Session not found: {session_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Session expired. Please upload a new CSV.",
                },
                status_code=404,
            )

        return templates.TemplateResponse(
            "simulator.html",
            {
                "request": request,
                "session_id": session_id,
                "analysis_id": None,  # None for session-based routes
                "route_prefix": "",  # Empty for session-based (/simulator/{id})
                "route_id": session_id,
                "created_at": session["created_at"].strftime("%Y-%m-%d %H:%M"),
                "results": None,
            },
        )

    except Exception as e:
        logger.error(f"Simulator GET error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=500
        )


@app.post("/simulator/{session_id}", response_class=HTMLResponse)
async def simulator_post(
    request: Request, session_id: str, rate_shock: int = 100, balance_shock: float = 5
):
    """Simulator POST: run shocks, return results."""
    try:
        logger.info(f"POST /simulator/{session_id} | rate={rate_shock} bps, balance={balance_shock}%")
        session = session_manager.get_session(session_id)

        if not session:
            logger.warning(f"Session not found: {session_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Session expired. Please upload a new CSV.",
                },
                status_code=404,
            )

        df = session["df"]

        # Determine which shocks to apply
        rate_shocks = [rate_shock] if rate_shock != 0 else []
        balance_shocks = [balance_shock] if balance_shock != 0 else []

        results = run_shocks(df, rate_shocks, balance_shocks)

        # Build comparison charts (returns figures)
        rate_shock_fig = None
        balance_shock_fig = None

        if rate_shocks:
            shock_bps = rate_shocks[0]
            df_shocked = results[f"{shock_bps:+d}bps_rate"]["df"]
            rate_shock_fig = build_shock_comparison_chart(
                df,
                df_shocked,
                f"{shock_bps:+d} bps Rate Shock",
                "rate",
                "rate_shocked",
            )

        if balance_shocks:
            shock_pct = balance_shocks[0]
            df_shocked = results[f"{shock_pct:+.0f}pct_balance"]["df"]
            balance_shock_fig = build_shock_comparison_chart(
                df,
                df_shocked,
                f"{shock_pct:+.0f}% Balance Shock",
                "balance",
                "balance_shocked",
            )

        # Convert figures to HTML for web display
        rate_shock_chart = rate_shock_fig.to_html(
            include_plotlyjs=False, config={"responsive": True}
        ) if rate_shock_fig else None
        balance_shock_chart = balance_shock_fig.to_html(
            include_plotlyjs=False, config={"responsive": True}
        ) if balance_shock_fig else None

        impact_table = generate_impact_table_html(results)

        logger.info(f"Simulator results generated for {session_id}")

        return templates.TemplateResponse(
            "simulator.html",
            {
                "request": request,
                "session_id": session_id,
                "created_at": session["created_at"].strftime("%Y-%m-%d %H:%M"),
                "results": results,
                "rate_shock_chart": rate_shock_chart,
                "balance_shock_chart": balance_shock_chart,
                "impact_table": impact_table,
            },
        )

    except Exception as e:
        logger.error(f"Simulator POST error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=500
        )


@app.get("/explain/{session_id}", response_class=HTMLResponse)
async def explain(request: Request, session_id: str):
    """Explain Engine: rule-based 3-section narrative."""
    try:
        logger.info(f"GET /explain/{session_id}")
        session = session_manager.get_session(session_id)

        if not session:
            logger.warning(f"Session not found: {session_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Session expired. Please upload a new CSV.",
                },
                status_code=404,
            )

        df = session["df"]
        explanation = generate_full_explanation(df)

        logger.info(f"Explanation generated for {session_id}")

        return templates.TemplateResponse(
            "explain.html",
            {
                "request": request,
                "session_id": session_id,
                "analysis_id": None,  # None for session-based routes
                "route_prefix": "",  # Empty for session-based (/explain/{id})
                "route_id": session_id,
                "created_at": session["created_at"].strftime("%Y-%m-%d %H:%M"),
                "what_matters": explanation["what_matters"],
                "what_risks": explanation["what_risks"],
                "whats_next": explanation["whats_next"],
            },
        )

    except Exception as e:
        logger.error(f"Explain error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=500
        )


# ============================================================================
# PHASE C: Analysis-Based Routes (Persistent History Mode)
# ============================================================================


@app.get("/snapshot/a/{analysis_id}", response_class=HTMLResponse)
async def snapshot_analysis(request: Request, analysis_id: int):
    """
    Borrower Snapshot from persisted analysis.
    Auth-required. Loads parquet file, computes KPIs, renders snapshot.
    """
    try:
        logger.info(f"GET /snapshot/a/{analysis_id}")
        current_user = get_current_user(request)

        # Redirect to login if not authenticated
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)

        # Verify user owns this analysis
        user_id = current_user["user_id"]
        analysis = db.get_analysis(analysis_id, user_id)

        if not analysis:
            logger.warning(f"Analysis {analysis_id} not found or not owned by user {user_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis not found or access denied.",
                },
                status_code=404,
            )

        # Load parquet file
        analysis_file = db.get_analysis_file(analysis_id, user_id)
        if not analysis_file:
            logger.warning(f"Analysis file not found for analysis {analysis_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis data not found.",
                },
                status_code=404,
            )

        parquet_path = BASE_DIR / analysis_file["stored_path"]
        if not parquet_path.exists():
            logger.warning(f"Parquet file not found: {parquet_path}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis data file not found on disk.",
                },
                status_code=404,
            )

        # Load dataframe from parquet
        df = pd.read_parquet(str(parquet_path))

        # Compute KPIs and flags
        kpis = compute_kpis(df)
        flags = detect_flags(df)

        kpi_html = format_kpi_tiles_html(kpis)

        # Build figures
        balance_fig = build_balance_chart(df)
        rate_fig = build_rate_chart(df)

        balance_chart = balance_fig.to_html(
            include_plotlyjs="cdn", div_id="balance_chart", config={"responsive": True}
        )
        rate_chart = rate_fig.to_html(
            include_plotlyjs=False, div_id="rate_chart", config={"responsive": True}
        )

        narrative = generate_kpi_narrative(kpis, flags)

        has_flags = any(
            [
                flags.get("volatility_spike"),
                flags.get("trend_change"),
                flags.get("missing_dates"),
                flags.get("outlier_count", 0) > 0,
            ]
        )

        # M3: Load exports for this analysis
        exports = db.list_exports_for_analysis(analysis_id, user_id)

        # M3.5: Load trends for all windows (30/90/180) for snapshot detail
        trends_data = {}
        from core.trends import TREND_WINDOWS
        import json
        for window_days in TREND_WINDOWS:
            window_trends = db.get_trends_for_analysis_window(analysis_id, user_id, window_days)
            if window_trends:
                # Parse metrics_json and organize by series
                trends_data[window_days] = {}
                for trend in window_trends:
                    try:
                        metrics = json.loads(trend["metrics_json"])
                        trends_data[window_days][trend["series_name"]] = {
                            "metrics": metrics,
                            "confidence": trend["confidence"],
                            "computed_at": trend["computed_at"],
                        }
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse metrics_json for trend {trend['id']}")
                        pass

        logger.info(f"Snapshot rendered for analysis {analysis_id}")

        return templates.TemplateResponse(
            "snapshot.html",
            {
                "request": request,
                "session_id": None,  # None for analysis-based routes
                "analysis_id": analysis_id,
                "route_prefix": "a/",  # For building links to /simulator/a/{id}, /explain/a/{id}
                "route_id": analysis_id,
                "analysis_info": {
                    "filename": analysis["filename"],
                    "uploaded_at": analysis.get("uploaded_at", "N/A"),
                    "date_min": analysis.get("date_min"),
                    "date_max": analysis.get("date_max"),
                    "row_count": analysis.get("row_count"),
                },
                "exports": exports,
                "kpi_html": kpi_html,
                "balance_chart": balance_chart,
                "rate_chart": rate_chart,
                "flags": flags,
                "has_flags": has_flags,
                "balance_stdev": kpis["balance_stdev"],
                "narrative": narrative,
                "is_from_history": True,
                "trends_data": trends_data,  # M3.5: Trend metrics by window
            },
        )

    except Exception as e:
        logger.error(f"Snapshot analysis error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=500
        )


@app.get("/simulator/a/{analysis_id}", response_class=HTMLResponse)
async def simulator_analysis_get(request: Request, analysis_id: int):
    """Simulator GET: show form for persisted analysis."""
    try:
        logger.info(f"GET /simulator/a/{analysis_id}")
        current_user = get_current_user(request)

        # Redirect to login if not authenticated
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)

        # Verify user owns this analysis
        user_id = current_user["user_id"]
        analysis = db.get_analysis(analysis_id, user_id)

        if not analysis:
            logger.warning(f"Analysis {analysis_id} not found or not owned by user {user_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis not found or access denied.",
                },
                status_code=404,
            )

        return templates.TemplateResponse(
            "simulator.html",
            {
                "request": request,
                "session_id": None,  # None for analysis-based routes
                "analysis_id": analysis_id,
                "route_prefix": "a/",  # For building links to /snapshot/a/{id}, /explain/a/{id}
                "route_id": analysis_id,
                "analysis_info": {
                    "filename": analysis["filename"],
                    "uploaded_at": analysis.get("uploaded_at", "N/A"),
                    "date_min": analysis.get("date_min"),
                    "date_max": analysis.get("date_max"),
                    "row_count": analysis.get("row_count"),
                },
                "exports": db.list_exports_for_analysis(analysis_id, user_id),
                "is_from_history": True,
            },
        )

    except Exception as e:
        logger.error(f"Simulator analysis GET error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=500
        )


@app.post("/simulator/a/{analysis_id}", response_class=HTMLResponse)
async def simulator_analysis_post(
    request: Request, analysis_id: int, rate_shock: int = 100, balance_shock: float = 5
):
    """Simulator POST: run shocks on persisted analysis."""
    try:
        logger.info(f"POST /simulator/a/{analysis_id} | rate={rate_shock} bps, balance={balance_shock}%")
        current_user = get_current_user(request)

        # Redirect to login if not authenticated
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)

        # Verify user owns this analysis
        user_id = current_user["user_id"]
        analysis = db.get_analysis(analysis_id, user_id)

        if not analysis:
            logger.warning(f"Analysis {analysis_id} not found or not owned by user {user_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis not found or access denied.",
                },
                status_code=404,
            )

        # Load parquet file
        analysis_file = db.get_analysis_file(analysis_id, user_id)
        if not analysis_file:
            logger.warning(f"Analysis file not found for analysis {analysis_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis data not found.",
                },
                status_code=404,
            )

        parquet_path = BASE_DIR / analysis_file["stored_path"]
        if not parquet_path.exists():
            logger.warning(f"Parquet file not found: {parquet_path}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis data file not found on disk.",
                },
                status_code=404,
            )

        # Load dataframe from parquet
        df = pd.read_parquet(str(parquet_path))

        # Determine which shocks to apply
        rate_shocks = [rate_shock] if rate_shock != 0 else []
        balance_shocks = [balance_shock] if balance_shock != 0 else []

        results = run_shocks(df, rate_shocks, balance_shocks)

        # Build comparison charts
        rate_shock_fig = None
        balance_shock_fig = None

        if rate_shocks:
            shock_bps = rate_shocks[0]
            df_shocked = results[f"{shock_bps:+d}bps_rate"]["df"]
            rate_shock_fig = build_shock_comparison_chart(
                df,
                df_shocked,
                f"{shock_bps:+d} bps Rate Shock",
                "rate",
                "rate_shocked",
            )

        if balance_shocks:
            shock_pct = balance_shocks[0]
            df_shocked = results[f"{shock_pct:+.0f}pct_balance"]["df"]
            balance_shock_fig = build_shock_comparison_chart(
                df,
                df_shocked,
                f"{shock_pct:+.0f}% Balance Shock",
                "balance",
                "balance_shocked",
            )

        # Convert figures to HTML
        rate_shock_chart = (
            rate_shock_fig.to_html(
                include_plotlyjs=False, config={"responsive": True}
            )
            if rate_shock_fig
            else None
        )
        balance_shock_chart = (
            balance_shock_fig.to_html(
                include_plotlyjs=False, config={"responsive": True}
            )
            if balance_shock_fig
            else None
        )

        impact_table = generate_impact_table_html(results)

        logger.info(f"Simulator results generated for analysis {analysis_id}")

        return templates.TemplateResponse(
            "simulator.html",
            {
                "request": request,
                "analysis_id": analysis_id,
                "analysis_info": {
                    "filename": analysis["filename"],
                    "uploaded_at": analysis.get("uploaded_at", "N/A"),
                    "date_min": analysis.get("date_min"),
                    "date_max": analysis.get("date_max"),
                    "row_count": analysis.get("row_count"),
                },
                "results": results,
                "rate_shock_chart": rate_shock_chart,
                "balance_shock_chart": balance_shock_chart,
                "impact_table": impact_table,
                "is_from_history": True,
            },
        )

    except Exception as e:
        logger.error(f"Simulator analysis POST error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=500
        )


@app.get("/explain/a/{analysis_id}", response_class=HTMLResponse)
async def explain_analysis(request: Request, analysis_id: int):
    """Explain Engine for persisted analysis."""
    try:
        logger.info(f"GET /explain/a/{analysis_id}")
        current_user = get_current_user(request)

        # Redirect to login if not authenticated
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)

        # Verify user owns this analysis
        user_id = current_user["user_id"]
        analysis = db.get_analysis(analysis_id, user_id)

        if not analysis:
            logger.warning(f"Analysis {analysis_id} not found or not owned by user {user_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis not found or access denied.",
                },
                status_code=404,
            )

        # Load parquet file
        analysis_file = db.get_analysis_file(analysis_id, user_id)
        if not analysis_file:
            logger.warning(f"Analysis file not found for analysis {analysis_id}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis data not found.",
                },
                status_code=404,
            )

        parquet_path = BASE_DIR / analysis_file["stored_path"]
        if not parquet_path.exists():
            logger.warning(f"Parquet file not found: {parquet_path}")
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error": "Analysis data file not found on disk.",
                },
                status_code=404,
            )

        # Load dataframe from parquet
        df = pd.read_parquet(str(parquet_path))
        explanation = generate_full_explanation(df)

        logger.info(f"Explanation generated for analysis {analysis_id}")

        return templates.TemplateResponse(
            "explain.html",
            {
                "request": request,
                "session_id": None,  # None for analysis-based routes
                "analysis_id": analysis_id,
                "route_prefix": "a/",  # For building links to /snapshot/a/{id}, /simulator/a/{id}
                "route_id": analysis_id,
                "analysis_info": {
                    "filename": analysis["filename"],
                    "uploaded_at": analysis.get("uploaded_at", "N/A"),
                    "date_min": analysis.get("date_min"),
                    "date_max": analysis.get("date_max"),
                    "row_count": analysis.get("row_count"),
                },
                "exports": db.list_exports_for_analysis(analysis_id, user_id),
                "what_matters": explanation["what_matters"],
                "what_risks": explanation["what_risks"],
                "whats_next": explanation["whats_next"],
                "is_from_history": True,
            },
        )

    except Exception as e:
        logger.error(f"Explain analysis error: {str(e)}")
        return templates.TemplateResponse(
            "error.html", {"request": request, "error": str(e)}, status_code=500
        )


# ============================================================================
# PHASE 2: PDF Export Routes
# ============================================================================


@app.post("/snapshot/{session_id}/export-pdf")
async def export_snapshot_pdf(request: Request, session_id: str, analysis_id: int = None):
    """Export Snapshot page to PDF. M3: Create export record if analysis_id provided."""
    try:
        logger.info(f"POST /snapshot/{session_id}/export-pdf (analysis_id={analysis_id})")
        session = session_manager.get_session(session_id)

        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(
                status_code=404, detail="Session expired or not found"
            )

        df = session["df"]
        kpis = compute_kpis(df)
        flags = detect_flags(df)

        # Generate figure objects
        balance_fig = build_balance_chart(df)
        rate_fig = build_rate_chart(df)
        narrative = generate_kpi_narrative(kpis, flags)

        # Generate PDF
        generator = SnapshotPDFGenerator(
            session_id=session_id,
            df=df,
            kpis=kpis,
            flags=flags,
            balance_chart=balance_fig,
            rate_chart=rate_fig,
            narrative=narrative,
            exports_dir=str(EXPORTS_DIR),
        )
        pdf_path = generator.generate()

        # M3: If user is logged in and analysis_id is provided, create export record
        current_user = get_current_user(request)
        export_record_id = None
        if current_user and analysis_id:
            try:
                # Verify user owns this analysis
                analysis = db.get_analysis(analysis_id, current_user["user_id"])
                if analysis:
                    # Create export record
                    file_size = Path(pdf_path).stat().st_size if Path(pdf_path).exists() else None
                    export_record_id = db.create_export(
                        user_id=current_user["user_id"],
                        analysis_id=analysis_id,
                        file_path=str(Path(pdf_path).relative_to(BASE_DIR)),
                        report_kind="snapshot_pdf",
                        file_size=file_size,
                    )
                    logger.info(f"Export record created: {export_record_id} for analysis {analysis_id}")
                else:
                    logger.warning(f"User {current_user['user_id']} does not own analysis {analysis_id}")
            except Exception as e:
                logger.warning(f"Failed to create export record (continuing with file): {str(e)}")
                # M3.75: Audit export record failure
                policy_log_event(
                    db=db,
                    user_id=current_user["user_id"] if current_user else None,
                    event_kind="export_record_failed",
                    details_json=json.dumps({"error": str(e), "analysis_id": analysis_id, "kind": "snapshot_pdf"}),
                    analysis_id=analysis_id,
                    request_id=getattr(request.state, "request_id", None),
                )

        # M3.75: Audit export success
        policy_log_event(
            db=db,
            user_id=current_user["user_id"] if current_user else None,
            event_kind="export_pdf",
            details_json=json.dumps({"kind": "snapshot_pdf", "session_id": session_id}),
            session_id=session_id,
            request_id=getattr(request.state, "request_id", None),
        )

        # Return download link
        filename = Path(pdf_path).name
        return JSONResponse(
            {
                "success": True,
                "filename": filename,
                "download_url": f"/exports/{filename}",
                "size_mb": round(Path(pdf_path).stat().st_size / (1024 * 1024), 2),
                "export_id": export_record_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Snapshot PDF export error: {str(e)}")
        return JSONResponse(
            {"success": False, "error": str(e)}, status_code=500
        )


@app.post("/simulator/{session_id}/export-pdf")
async def export_simulator_pdf(
    request: Request,
    session_id: str,
    analysis_id: int = None,
    rate_shock: int = 100,
    balance_shock: float = 5,
):
    """Export Simulator page to PDF. M3: Create export record if analysis_id provided."""
    try:
        logger.info(
            f"POST /simulator/{session_id}/export-pdf (analysis_id={analysis_id}) | rate={rate_shock}, balance={balance_shock}"
        )
        session = session_manager.get_session(session_id)

        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(
                status_code=404, detail="Session expired or not found"
            )

        df = session["df"]

        # Apply shocks
        rate_shocks = [rate_shock] if rate_shock != 0 else []
        balance_shocks = [balance_shock] if balance_shock != 0 else []
        results = run_shocks(df, rate_shocks, balance_shocks)

        # Build comparison figures
        rate_shock_fig = None
        balance_shock_fig = None

        if rate_shocks:
            shock_bps = rate_shocks[0]
            df_shocked = results[f"{shock_bps:+d}bps_rate"]["df"]
            rate_shock_fig = build_shock_comparison_chart(
                df,
                df_shocked,
                f"{shock_bps:+d} bps Rate Shock",
                "rate",
                "rate_shocked",
            )

        if balance_shocks:
            shock_pct = balance_shocks[0]
            df_shocked = results[f"{shock_pct:+.0f}pct_balance"]["df"]
            balance_shock_fig = build_shock_comparison_chart(
                df,
                df_shocked,
                f"{shock_pct:+.0f}% Balance Shock",
                "balance",
                "balance_shocked",
            )

        # Generate PDF
        generator = SimulatorPDFGenerator(
            session_id=session_id,
            baseline_df=df,
            results=results,
            rate_shock_chart=rate_shock_fig,
            balance_shock_chart=balance_shock_fig,
            exports_dir=str(EXPORTS_DIR),
        )
        pdf_path = generator.generate()

        # M3: If user is logged in and analysis_id is provided, create export record
        current_user = get_current_user(request)
        export_record_id = None
        if current_user and analysis_id:
            try:
                # Verify user owns this analysis
                analysis = db.get_analysis(analysis_id, current_user["user_id"])
                if analysis:
                    # Create export record
                    file_size = Path(pdf_path).stat().st_size if Path(pdf_path).exists() else None
                    export_record_id = db.create_export(
                        user_id=current_user["user_id"],
                        analysis_id=analysis_id,
                        file_path=str(Path(pdf_path).relative_to(BASE_DIR)),
                        report_kind="simulator_pdf",
                        file_size=file_size,
                    )
                    logger.info(f"Export record created: {export_record_id} for analysis {analysis_id}")
                else:
                    logger.warning(f"User {current_user['user_id']} does not own analysis {analysis_id}")
            except Exception as e:
                logger.warning(f"Failed to create export record (continuing with file): {str(e)}")

        # Return download link
        filename = Path(pdf_path).name
        return JSONResponse(
            {
                "success": True,
                "filename": filename,
                "download_url": f"/exports/{filename}",
                "size_mb": round(Path(pdf_path).stat().st_size / (1024 * 1024), 2),
                "export_id": export_record_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simulator PDF export error: {str(e)}")
        return JSONResponse(
            {"success": False, "error": str(e)}, status_code=500
        )


@app.post("/explain/{session_id}/export-pdf")
async def export_explain_pdf(request: Request, session_id: str, analysis_id: int = None):
    """Export Explain page to PDF. M3: Create export record if analysis_id provided."""
    try:
        logger.info(f"POST /explain/{session_id}/export-pdf (analysis_id={analysis_id})")
        session = session_manager.get_session(session_id)

        if not session:
            logger.warning(f"Session not found: {session_id}")
            raise HTTPException(
                status_code=404, detail="Session expired or not found"
            )

        df = session["df"]
        explanation = generate_full_explanation(df)

        # Generate PDF
        generator = ExplainPDFGenerator(
            session_id=session_id,
            explanation=explanation,
            exports_dir=str(EXPORTS_DIR),
        )
        pdf_path = generator.generate()

        # M3: If user is logged in and analysis_id is provided, create export record
        current_user = get_current_user(request)
        export_record_id = None
        if current_user and analysis_id:
            try:
                # Verify user owns this analysis
                analysis = db.get_analysis(analysis_id, current_user["user_id"])
                if analysis:
                    # Create export record
                    file_size = Path(pdf_path).stat().st_size if Path(pdf_path).exists() else None
                    export_record_id = db.create_export(
                        user_id=current_user["user_id"],
                        analysis_id=analysis_id,
                        file_path=str(Path(pdf_path).relative_to(BASE_DIR)),
                        report_kind="explain_pdf",
                        file_size=file_size,
                    )
                    logger.info(f"Export record created: {export_record_id} for analysis {analysis_id}")
                else:
                    logger.warning(f"User {current_user['user_id']} does not own analysis {analysis_id}")
            except Exception as e:
                logger.warning(f"Failed to create export record (continuing with file): {str(e)}")

        # Return download link
        filename = Path(pdf_path).name
        return JSONResponse(
            {
                "success": True,
                "filename": filename,
                "download_url": f"/exports/{filename}",
                "size_mb": round(Path(pdf_path).stat().st_size / (1024 * 1024), 2),
                "export_id": export_record_id,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explain PDF export error: {str(e)}")
        return JSONResponse(
            {"success": False, "error": str(e)}, status_code=500
        )


# ============================================================================
# PHASE D (M3): Canonical Export Routes (Analysis-based, persistent mode)
# ============================================================================

@app.post("/snapshot/a/{analysis_id}/export-pdf")
async def export_snapshot_analysis_pdf(request: Request, analysis_id: int):
    """Export snapshot for persisted analysis. M3: Auth guard + ownership check."""
    try:
        logger.info(f"POST /snapshot/a/{analysis_id}/export-pdf")
        current_user = get_current_user(request)

        if not current_user:
            return RedirectResponse(url="/login", status_code=302)

        user_id = current_user["user_id"]

        # Ownership verification
        analysis = db.get_analysis(analysis_id, user_id)
        if not analysis:
            logger.warning(f"User {user_id} attempted to access analysis {analysis_id}")
            raise HTTPException(status_code=404, detail="Analysis not found")

        # Load analysis file and parquet
        analysis_file = db.get_analysis_file(analysis_id, user_id)
        if not analysis_file:
            raise HTTPException(status_code=404, detail="Analysis file not found")

        parquet_path = BASE_DIR / analysis_file["stored_path"]
        df = pd.read_parquet(str(parquet_path))

        # Compute KPIs and generate PDF
        kpis = compute_kpis(df)
        flags = detect_flags(df)
        balance_fig = build_balance_chart(df)
        rate_fig = build_rate_chart(df)
        narrative = generate_kpi_narrative(kpis, flags)

        generator = SnapshotPDFGenerator(
            session_id=f"analysis_{analysis_id}",
            df=df,
            kpis=kpis,
            flags=flags,
            balance_chart=balance_fig,
            rate_chart=rate_fig,
            narrative=narrative,
            exports_dir=str(EXPORTS_DIR),
        )
        pdf_path = generator.generate()

        # Create export record
        file_size = Path(pdf_path).stat().st_size if Path(pdf_path).exists() else None
        export_record_id = db.create_export(
            user_id=user_id,
            analysis_id=analysis_id,
            file_path=str(Path(pdf_path).relative_to(BASE_DIR)),
            report_kind="snapshot_pdf",
            file_size=file_size,
        )

        filename = Path(pdf_path).name
        logger.info(f"Snapshot analysis PDF exported: {filename} (export_id={export_record_id})")

        return JSONResponse({
            "success": True,
            "filename": filename,
            "download_url": f"/exports/{filename}",
            "size_mb": round(file_size / (1024 * 1024), 2) if file_size else None,
            "export_id": export_record_id,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Snapshot analysis PDF export error: {str(e)}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/simulator/a/{analysis_id}/export-pdf")
async def export_simulator_analysis_pdf(
    request: Request, analysis_id: int, rate_shock: int = 0, balance_shock: float = 0.0
):
    """Export simulator results for persisted analysis. M3: Auth guard + ownership check."""
    try:
        logger.info(f"POST /simulator/a/{analysis_id}/export-pdf (rate_shock={rate_shock}, balance_shock={balance_shock})")
        current_user = get_current_user(request)

        if not current_user:
            return RedirectResponse(url="/login", status_code=302)

        user_id = current_user["user_id"]

        # Ownership verification
        analysis = db.get_analysis(analysis_id, user_id)
        if not analysis:
            logger.warning(f"User {user_id} attempted to access analysis {analysis_id}")
            raise HTTPException(status_code=404, detail="Analysis not found")

        # Load analysis file and parquet
        analysis_file = db.get_analysis_file(analysis_id, user_id)
        if not analysis_file:
            raise HTTPException(status_code=404, detail="Analysis file not found")

        parquet_path = BASE_DIR / analysis_file["stored_path"]
        df = pd.read_parquet(str(parquet_path))

        # Compute baseline KPIs
        baseline_kpis = compute_kpis(df)
        baseline_flags = detect_flags(df)

        # Apply shocks
        rate_shock_bps = int(rate_shock)
        balance_shock_pct = float(balance_shock)

        rate_shocks = [rate_shock_bps] if rate_shock_bps != 0 else []
        balance_shocks = [balance_shock_pct] if balance_shock_pct != 0 else []
        results = run_shocks(df, rate_shocks, balance_shocks)

        # Get the shocked dataframe (use the first shock result if available)
        if rate_shocks:
            shocked_key = f"{rate_shock_bps:+d}bps_rate"
            shocked_df = results[shocked_key]["df"]
        elif balance_shocks:
            shocked_key = f"{balance_shock_pct:+.0f}pct_balance"
            shocked_df = results[shocked_key]["df"]
        else:
            shocked_df = df

        shocked_kpis = compute_kpis(shocked_df)

        # Generate charts
        balance_fig = build_balance_chart(df)
        rate_fig = build_rate_chart(df)
        shocked_balance_fig = build_balance_chart(shocked_df)
        shocked_rate_fig = build_rate_chart(shocked_df)

        # Generate PDF
        generator = SimulatorPDFGenerator(
            session_id=f"analysis_{analysis_id}",
            df=df,
            shocked_df=shocked_df,
            rate_shock_bps=rate_shock_bps,
            balance_shock_pct=balance_shock_pct,
            baseline_kpis=baseline_kpis,
            shocked_kpis=shocked_kpis,
            balance_chart=balance_fig,
            rate_chart=rate_fig,
            shocked_balance_chart=shocked_balance_fig,
            shocked_rate_chart=shocked_rate_fig,
            exports_dir=str(EXPORTS_DIR),
        )
        pdf_path = generator.generate()

        # Create export record
        file_size = Path(pdf_path).stat().st_size if Path(pdf_path).exists() else None
        export_record_id = db.create_export(
            user_id=user_id,
            analysis_id=analysis_id,
            file_path=str(Path(pdf_path).relative_to(BASE_DIR)),
            report_kind="simulator_pdf",
            file_size=file_size,
        )

        filename = Path(pdf_path).name
        logger.info(f"Simulator analysis PDF exported: {filename} (export_id={export_record_id})")

        return JSONResponse({
            "success": True,
            "filename": filename,
            "download_url": f"/exports/{filename}",
            "size_mb": round(file_size / (1024 * 1024), 2) if file_size else None,
            "export_id": export_record_id,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Simulator analysis PDF export error: {str(e)}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/explain/a/{analysis_id}/export-pdf")
async def export_explain_analysis_pdf(request: Request, analysis_id: int):
    """Export explanation for persisted analysis. M3: Auth guard + ownership check."""
    try:
        logger.info(f"POST /explain/a/{analysis_id}/export-pdf")
        current_user = get_current_user(request)

        if not current_user:
            return RedirectResponse(url="/login", status_code=302)

        user_id = current_user["user_id"]

        # Ownership verification
        analysis = db.get_analysis(analysis_id, user_id)
        if not analysis:
            logger.warning(f"User {user_id} attempted to access analysis {analysis_id}")
            raise HTTPException(status_code=404, detail="Analysis not found")

        # Load analysis file and parquet
        analysis_file = db.get_analysis_file(analysis_id, user_id)
        if not analysis_file:
            raise HTTPException(status_code=404, detail="Analysis file not found")

        parquet_path = BASE_DIR / analysis_file["stored_path"]
        df = pd.read_parquet(str(parquet_path))

        # Generate explanation
        kpis = compute_kpis(df)
        flags = detect_flags(df)
        narrative = generate_kpi_narrative(kpis, flags)
        rules = (df, kpis, flags)

        # Generate PDF
        generator = ExplainPDFGenerator(
            session_id=f"analysis_{analysis_id}",
            df=df,
            kpis=kpis,
            flags=flags,
            narrative=narrative,
            rules=rules,
            exports_dir=str(EXPORTS_DIR),
        )
        pdf_path = generator.generate()

        # Create export record
        file_size = Path(pdf_path).stat().st_size if Path(pdf_path).exists() else None
        export_record_id = db.create_export(
            user_id=user_id,
            analysis_id=analysis_id,
            file_path=str(Path(pdf_path).relative_to(BASE_DIR)),
            report_kind="explain_pdf",
            file_size=file_size,
        )

        filename = Path(pdf_path).name
        logger.info(f"Explain analysis PDF exported: {filename} (export_id={export_record_id})")

        return JSONResponse({
            "success": True,
            "filename": filename,
            "download_url": f"/exports/{filename}",
            "size_mb": round(file_size / (1024 * 1024), 2) if file_size else None,
            "export_id": export_record_id,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explain analysis PDF export error: {str(e)}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/exports/{filename}")
async def download_pdf(request: Request, filename: str):
    """Download generated PDF."""
    try:
        filepath = EXPORTS_DIR / filename

        if not filepath.exists():
            logger.warning(f"PDF not found: {filename}")
            raise HTTPException(status_code=404, detail="PDF not found")

        logger.info(f"Downloading PDF: {filename}")

        # M3.75: Audit download
        current_user = get_current_user(request)
        policy_log_event(
            db=db,
            user_id=current_user["user_id"] if current_user else None,
            event_kind="download_pdf",
            details_json=json.dumps({"filename": filename}),
            request_id=getattr(request.state, "request_id", None),
        )

        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/pdf",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF download error: {str(e)}")
        raise HTTPException(status_code=500, detail="Download failed")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/session/{session_id}")
async def get_session_meta(session_id: str):
    """Optional API endpoint: return session metadata."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    return {
        "session_id": session_id,
        "filename": session["filename"],
        "created_at": session["created_at"].isoformat(),
        "row_count": session["row_count"],
    }


# =============================================================================
# M3.75 Phase 2: Policy-Enforced API Endpoint
# =============================================================================

@app.get("/api/analyses/{analysis_id}/explain")
async def api_explain_analysis(request: Request, analysis_id: int):
    """
    M3.75: JSON API for explanation with rules_fired.
    Enforces user auth + ownership via middleware + policy_guard.
    """
    # Auth enforced by PolicyMiddleware (returns 403 for /api/* prefixes)
    current_user = get_current_user(request)
    if not current_user:
        return JSONResponse({"detail": "Authentication required"}, status_code=403)

    user_id = current_user["user_id"]

    # Ownership check
    analysis = db.get_analysis(analysis_id, user_id)
    if not analysis:
        return JSONResponse(
            {"detail": "Analysis not found or access denied"}, status_code=404
        )

    # Load parquet
    analysis_file = db.get_analysis_file(analysis_id, user_id)
    if not analysis_file:
        return JSONResponse({"detail": "Analysis data not found"}, status_code=404)

    parquet_path = BASE_DIR / analysis_file["stored_path"]
    if not parquet_path.exists():
        return JSONResponse(
            {"detail": "Analysis data file not found on disk"}, status_code=404
        )

    df = pd.read_parquet(str(parquet_path))
    explanation = generate_full_explanation(df)

    rules_fired = explanation.get("rules_fired", [])

    # M3.75: Audit API explain access
    policy_log_event(
        db=db,
        user_id=user_id,
        event_kind="api_explain",
        details_json=json.dumps({
            "analysis_id": analysis_id,
            "rules_fired": rules_fired,
        }),
        analysis_id=analysis_id,
        request_id=getattr(request.state, "request_id", None),
    )

    return JSONResponse({
        "analysis_id": analysis_id,
        "filename": analysis["filename"],
        "what_matters": explanation["what_matters"],
        "what_risks": explanation["what_risks"],
        "whats_next": explanation["whats_next"],
        "rules_fired": rules_fired,
    })


# Health check
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "active_sessions": len(session_manager.list_active_sessions()),
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Banker Analytics (Milestone 3.75)")
    uvicorn.run(app, host="127.0.0.1", port=8000)
