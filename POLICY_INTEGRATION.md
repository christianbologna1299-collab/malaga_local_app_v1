# Policy Integration Guide for Banker Analytics

## Overview

This document explains how to use `core/policy.py` to enforce **POLICY.md** rules in development and production.

---

## 1. Quick Start: Add Policy Enforcement to Routes

### Step 1: Import Policy Functions

Add this to the top of `app.py`:

```python
from core.policy import (
    policy_audit,
    policy_safe_fail,
    verify_user_owns_analysis,
    validate_filename,
    log_artifact_metadata,
    log_policy_violation,
    print_policy_summary,
)
```

### Step 2: Apply Audit Decorator

Wrap routes that need audit logging:

```python
@app.get("/snapshot/a/{analysis_id}", response_class=HTMLResponse)
@policy_audit("snapshot_analysis")  # Add this line
async def snapshot_analysis(request: Request, analysis_id: int):
    """Policy #9: Audit logging enabled"""
    ...
```

### Step 3: Add Ownership Checks

Use the verification function in your route:

```python
@app.get("/snapshot/a/{analysis_id}", response_class=HTMLResponse)
@policy_audit("snapshot_analysis")
async def snapshot_analysis(request: Request, analysis_id: int):
    """Policy #4: Hard user isolation via ownership check"""
    try:
        # Verify user owns this analysis (throws 404 if not)
        user_id = verify_user_owns_analysis(
            request,
            analysis_id,
            db,
            route_name="snapshot_analysis"
        )

        # ... rest of route implementation ...

    except HTTPException:
        raise  # Policy violation already logged
```

---

## 2. Core Policy Functions

### `verify_user_owns_analysis(request, analysis_id, db, route_name)`

**Policy Rule**: Policy #4 — "No ownership check, no merge"

**Purpose**: Verify current user owns analysis_id before access

**Usage**:
```python
user_id = verify_user_owns_analysis(request, analysis_id, db, "my_route")

# If verification fails:
# - HTTPException(404) is raised
# - POLICY VIOLATION is logged with request context
# - Action is blocked
```

**Logged Context**:
- `request_id`: Unique ID for this request
- `user_id`: Attempting user
- `analysis_id`: Analysis they tried to access
- `route`: Route name
- `errors`: "User {id} does not own analysis {id}"

---

### `policy_audit(route_name)` Decorator

**Policy Rule**: Policy #9 — "If a banker asks 'what happened,' we can answer"

**Purpose**: Automatic request/response logging with tracing

**Usage**:
```python
@app.post("/snapshot/a/{analysis_id}/export-pdf")
@policy_audit("snapshot_export_pdf")
async def export_snapshot_pdf(request: Request, analysis_id: int):
    ...
```

**Logs**:
- ✓ Success: `✓ Route snapshot_export_pdf completed successfully`
- ⚠ HTTP Error: `⚠ Route snapshot_export_pdf returned HTTP 403`
- ✗ Exception: `✗ Route snapshot_export_pdf failed with exception`

**Context Added to All Logs**:
```json
{
  "request_id": "a1b2c3d4",
  "route": "snapshot_export_pdf",
  "user_id": 5,
  "analysis_id": 123,
  "scenario_id": null,
  "export_id": null,
  "duration_ms": 245.67,
  "errors": []
}
```

---

### `policy_safe_fail(operation_name)` Decorator

**Policy Rule**: Policy #6 — "Failure must not destroy history or trust"

**Purpose**: Fail gracefully without corrupting state

**Usage**:
```python
@policy_safe_fail("trend_computation")
def compute_trends(df, file_hash, user_id, analysis_id):
    # If this fails, it logs but doesn't throw
    # Caller gets None and continues
    ...
```

**Example: Non-Fatal Trend Computation**:
```python
# In upload endpoint, after parquet save:
@policy_safe_fail("trend_computation")
def compute_and_store_trends():
    trends = compute_trends(
        df=df_clean,
        file_hash=file_hash,
        user_id=user_id,
        analysis_id=analysis_id
    )
    for trend in trends:
        db.create_trend(...)

# If trend computation fails:
# - Warning is logged: "⚠ Operation trend_computation failed (non-fatal)"
# - None is returned
# - Upload continues successfully
# - User sees: "Analysis saved (trends not available)"
```

---

### `validate_filename(filename)`

**Policy Rule**: Policy #5 — "Never trust user-supplied paths"

**Purpose**: Prevent path traversal attacks

**Usage**:
```python
try:
    safe_filename = validate_filename(user_supplied_filename)
except ValueError as e:
    log_policy_violation("path_traversal", detail=str(e))
    raise HTTPException(400, "Invalid filename")
```

**Rejected Patterns**:
- `../`, `..\\` (path traversal)
- `/`, `\\` (directory separators)
- Empty strings

**Example**:
```python
validate_filename("analysis.csv")          # ✓ OK
validate_filename("../../../etc/passwd")   # ✗ REJECTED
validate_filename("data/analysis.csv")     # ✗ REJECTED (contains /)
```

---

### `validate_determinism_contract(analysis_id, engine_version, inputs_hash, computed_at)`

**Policy Rule**: Policy #3 — "If we cannot reproduce output tomorrow, it does not ship"

**Purpose**: Ensure deterministic outputs are properly versioned

**Usage**:
```python
# When storing a computed result (KPI, trend, scenario):
validate_determinism_contract(
    analysis_id=123,
    engine_version="v1.0",
    inputs_hash="sha256_of_inputs",
    computed_at=datetime.now()
)

# Validates presence of all required fields
# Logs for auditability
```

**Logs**:
```
Determinism contract: analysis=123, version=v1.0, inputs_hash=abc123, computed_at=2026-02-06T14:30:00
```

---

### `log_artifact_metadata(artifact_id, artifact_type, user_id, analysis_id, template_version, file_hash)`

**Policy Rule**: Policy #11 — "Every artifact can defend itself"

**Purpose**: Create audit trail for PDFs, Excel reports, and data artifacts

**Usage**:
```python
# After creating a PDF export:
log_artifact_metadata(
    artifact_id=export_id,
    artifact_type="snapshot_pdf",
    user_id=current_user["user_id"],
    analysis_id=analysis_id,
    template_version="snapshot_v3.0",
    file_hash="sha256_of_pdf"
)
```

**Logged**:
```json
{
  "artifact_id": 456,
  "artifact_type": "snapshot_pdf",
  "user_id": 5,
  "analysis_id": 123,
  "template_version": "snapshot_v3.0",
  "file_hash": "e3b0c44298fc1c149a...",
  "created_at": "2026-02-06T14:30:45.123456"
}
```

---

### `log_policy_violation(violation_type, user_id, analysis_id, detail)`

**Policy Rule**: Policy #4, #5 — Security & compliance review

**Purpose**: Log security violations for incident response

**Usage**:
```python
log_policy_violation(
    violation_type="cross_user_access_attempt",
    user_id=5,
    analysis_id=999,
    detail="User 5 tried to access analysis 999 owned by user 3"
)
```

**Log Level**: ERROR (always visible)

**Common Violation Types**:
- `cross_user_access_attempt`
- `path_traversal_detected`
- `missing_ownership_check`
- `authentication_bypass_attempt`
- `unauthorized_export_access`

---

## 3. Integration Examples

### Example 1: Snapshot Route with Full Policy

```python
@app.get("/snapshot/a/{analysis_id}", response_class=HTMLResponse)
@policy_audit("snapshot_analysis")
async def snapshot_analysis(request: Request, analysis_id: int):
    """
    Policy Enforcement:
    - #4 Hard isolation: ownership check required
    - #9 Auditability: all access logged with request_id + duration
    """
    try:
        # Policy #4: Verify user owns analysis
        user_id = verify_user_owns_analysis(
            request,
            analysis_id,
            db,
            route_name="snapshot_analysis"
        )

        # Policy #5: Safely load parquet (path already validated)
        analysis_file = db.get_analysis_file(analysis_id, user_id)
        if not analysis_file:
            raise HTTPException(404, "Analysis data not found")

        parquet_path = BASE_DIR / analysis_file["stored_path"]
        df = pd.read_parquet(str(parquet_path))

        # Compute KPIs, trends, etc.
        kpis = compute_kpis(df)

        # Policy #11: Log that artifact was accessed
        log_artifact_metadata(
            artifact_id=analysis_id,
            artifact_type="snapshot_view",
            user_id=user_id,
            analysis_id=analysis_id,
            template_version="snapshot_v3.0"
        )

        return templates.TemplateResponse("snapshot.html", {...})

    except HTTPException:
        raise  # Already logged by verify_user_owns_analysis or policy_audit
```

---

### Example 2: Upload with Safe-Fail Trend Computation

```python
@app.post("/upload")
@policy_audit("upload")
async def upload(request: Request, file: UploadFile = File(...)):
    """
    Policy Enforcement:
    - #5 Data safety: validate + clean before storage
    - #3 Determinism: file_hash + version for reproducibility
    - #6 Safe-fail: trends are non-fatal (don't block upload)
    """
    try:
        # Parse and validate
        df = parse_csv(await file.read())
        validate_schema(df)
        df_clean = clean_data(df)

        current_user = get_current_user(request)
        if not current_user:
            return JSONResponse({"detail": "Login required"}, 400)

        # Create analysis record (Policy #1: Single Source of Truth)
        analysis_id = db.create_analysis(
            user_id=current_user["user_id"],
            filename=validate_filename(file.filename),  # Policy #5
            row_count=len(df_clean)
        )

        # Save parquet with hash (Policy #3: Determinism)
        parquet_path = ANALYSES_DIR / f"{analysis_id}.parquet"
        df_clean.to_parquet(str(parquet_path), index=False)
        file_hash = compute_file_hash(str(parquet_path))

        db.create_analysis_file(
            user_id=current_user["user_id"],
            analysis_id=analysis_id,
            stored_path=str(parquet_path.relative_to(BASE_DIR)),
            file_hash=file_hash
        )

        # Policy #6: Safe-fail — trends don't block upload
        @policy_safe_fail("trend_computation")
        def compute_trends_safe():
            from core.trends import compute_trends
            trends = compute_trends(
                df=df_clean,
                user_id=current_user["user_id"],
                analysis_id=analysis_id,
                file_hash=file_hash
            )
            for trend in trends:
                if not db.trend_exists(trend.inputs_hash):
                    db.create_trend(...)
            return len(trends)

        trend_count = compute_trends_safe()

        return JSONResponse({
            "analysis_id": analysis_id,
            "trends_computed": trend_count or 0,
            "filename": file.filename,
            "rows": len(df_clean)
        })

    except ValueError as e:
        log_policy_violation("validation_error", detail=str(e))
        return JSONResponse({"detail": str(e)}, 400)
```

---

## 4. Logging Output Examples

### Successful Route Execution

```
2026-02-06 14:30:45 [app] INFO: ✓ Route snapshot_analysis completed successfully
  request_id: a1b2c3d4
  route: snapshot_analysis
  user_id: 5
  analysis_id: 123
  scenario_id: null
  export_id: null
  duration_ms: 245.67
  errors: []
```

### Policy Violation: Cross-User Access

```
2026-02-06 14:31:12 [app] WARNING: POLICY VIOLATION: Cross-user analysis access denied
  request_id: b2c3d4e5
  user_id: 3
  analysis_id: 999
  route: snapshot_analysis
  errors: ['User 3 does not own analysis 999']
```

### Non-Fatal Operation Failure

```
2026-02-06 14:32:00 [app] WARNING: ⚠ Operation trend_computation failed (non-fatal)
  request_id: c3d4e5f6
  route: upload
  user_id: 5
  analysis_id: 123
  errors: ['trend_computation: Index out of range']
```

---

## 5. Development Checklist

When adding a new route that accesses user data:

- [ ] **Policy #4**: Add `verify_user_owns_analysis()` call
- [ ] **Policy #9**: Add `@policy_audit("route_name")` decorator
- [ ] **Policy #5**: Use `validate_filename()` for any user paths
- [ ] **Policy #1**: Call compute functions, not repeat logic
- [ ] **Policy #3**: Store `engine_version` + `inputs_hash` for derived outputs
- [ ] **Policy #6**: Wrap optional operations in `@policy_safe_fail()`
- [ ] **Policy #11**: Call `log_artifact_metadata()` after creating artifacts

---

## 6. Running Policy Validation

### Print Policy Summary

```python
from core.policy import print_policy_summary

print_policy_summary()
```

Output:
```
======================================================================
BANKER ANALYTICS — ENGINEERING POLICY ENFORCEMENT
======================================================================

Priority: correctness > auditability > reliability > speed > new features

Core Principles:
  ✓ Deterministic-first: Same inputs → same outputs
  ✓ Single Source of Truth: No duplicate business logic
  ✓ Hard user isolation: user_id boundary enforced everywhere
  ✓ Safe-fail by design: Failures degrade gracefully; no silent corruption
  ✓ Auditability: Every artifact is defendable (what data, when, how, which version)
  ✓ Local-first: Works on Windows, no Docker, no cloud dependency

Architecture Layers:
  • routes: auth checks + input parsing + response rendering only
  • services: orchestration (load, compute, store)
  • domain: pure deterministic computations
  • db_layer: CRUD only (no business logic)
  • templates: presentation only (no calculations beyond formatting)

Ownership Checks Required For:
  • analysis_id
  • scenario_id
  • export_id
  • stored files

======================================================================
```

### Call at App Startup

```python
if __name__ == "__main__":
    print_policy_summary()  # Display policy on startup
    print("\nStarting Banker Analytics...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

---

## 7. Policy Enforcement in Tests

### Test User Isolation (Policy #4)

```python
def test_user_isolation():
    """Verify Policy #4: Hard user isolation"""

    # Create two users
    user_a_id = db.create_user("alice", hash_password("pass"))
    user_b_id = db.create_user("bob", hash_password("pass"))

    # Create analysis for user A
    analysis_id = db.create_analysis(
        user_id=user_a_id,
        filename="test.csv",
        row_count=100
    )

    # User B should NOT be able to access User A's analysis
    analysis = db.get_analysis(analysis_id, user_b_id)
    assert analysis is None, "User isolation violated!"

    # User B gets 404 (not 403) to hide analysis existence (Policy #4)
    response = client.get(f"/snapshot/a/{analysis_id}", cookies={"session": bob_session})
    assert response.status_code == 404
```

### Test Determinism (Policy #3)

```python
def test_determinism_contract():
    """Verify Policy #3: Determinism + reproducibility"""

    file_hash = "abc123"
    engine_version = "v1.0"
    inputs_hash1 = compute_inputs_hash(file_hash, 30, "balance")
    inputs_hash2 = compute_inputs_hash(file_hash, 30, "balance")

    # Same inputs → same hash
    assert inputs_hash1 == inputs_hash2

    # Different window → different hash
    inputs_hash3 = compute_inputs_hash(file_hash, 90, "balance")
    assert inputs_hash1 != inputs_hash3
```

### Test Safe-Fail (Policy #6)

```python
def test_safe_fail_trend_computation():
    """Verify Policy #6: Failures don't corrupt upload"""

    # Create bad data that will fail trend computation
    df_bad = pd.DataFrame({
        'date': [pd.NaT] * 10,  # All NaT
        'balance': [np.nan] * 10,
        'rate': [np.nan] * 10
    })

    # Upload should still succeed
    response = client.post(
        "/upload",
        files={"file": ("bad.csv", csv_bytes)},
        cookies={"session": alice_session}
    )

    assert response.status_code == 200
    assert "analysis_id" in response.json()
    # Trends are absent, but analysis is saved
```

---

## Summary

**Policy.py provides**:
- ✅ Automatic audit logging (Policy #9)
- ✅ Ownership verification decorators (Policy #4)
- ✅ Safe-fail patterns (Policy #6)
- ✅ Determinism validation (Policy #3)
- ✅ Artifact metadata logging (Policy #11)
- ✅ Policy violation alerts (Security)

**Next Steps**:
1. Import `core.policy` into `app.py`
2. Add `@policy_audit()` to routes
3. Add `verify_user_owns_analysis()` calls
4. Wrap non-fatal operations in `@policy_safe_fail()`
5. Run tests with policy checks enabled

---

**For questions or policy updates, see POLICY.md**
