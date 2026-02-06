# Policy Enforcement — Quick Reference

## TL;DR: Copy-Paste Quick Start

### 1. Add to app.py imports

```python
from core.policy import (
    policy_audit,
    policy_safe_fail,
    verify_user_owns_analysis,
    validate_filename,
    log_artifact_metadata,
)
```

### 2. Protect a Route (Add Two Lines)

**Before**:
```python
@app.get("/snapshot/a/{analysis_id}")
async def snapshot_analysis(request: Request, analysis_id: int):
    analysis = db.get_analysis(analysis_id, user_id)
    ...
```

**After**:
```python
@app.get("/snapshot/a/{analysis_id}")
@policy_audit("snapshot_analysis")  # ← ADD THIS
async def snapshot_analysis(request: Request, analysis_id: int):
    user_id = verify_user_owns_analysis(request, analysis_id, db, "snapshot_analysis")  # ← ADD THIS
    ...
```

---

## Policy Enforcement Checklist

| Policy # | Rule | Function | Example |
|----------|------|----------|---------|
| **#4** | Hard user isolation | `verify_user_owns_analysis()` | `user_id = verify_user_owns_analysis(req, aid, db, "route")` |
| **#9** | Audit logging | `@policy_audit("name")` | `@app.get("/path") @policy_audit("route_name")` |
| **#5** | Safe filenames | `validate_filename()` | `safe = validate_filename(user_input)` |
| **#6** | Non-fatal ops | `@policy_safe_fail("op")` | `@policy_safe_fail("trend_compute")` |
| **#11** | Artifact metadata | `log_artifact_metadata()` | After creating PDF: `log_artifact_metadata(id, "pdf", uid, aid)` |
| **#3** | Determinism | `validate_determinism_contract()` | After storing computed result |

---

## Common Patterns

### Pattern 1: Protected Read Route

```python
@app.get("/snapshot/a/{analysis_id}")
@policy_audit("snapshot_read")
async def snapshot(request: Request, analysis_id: int):
    # Owners only
    user_id = verify_user_owns_analysis(request, analysis_id, db, "snapshot_read")

    # Load data
    analysis = db.get_analysis(analysis_id, user_id)
    ...

    return templates.TemplateResponse("snapshot.html", {...})
```

### Pattern 2: Non-Fatal Background Operation

```python
@policy_safe_fail("trend_computation")
def safe_compute_trends(df, user_id, analysis_id, file_hash):
    trends = compute_trends(df, user_id, analysis_id, file_hash)
    for trend in trends:
        db.create_trend(...)
    return len(trends)

# In upload route:
trend_count = safe_compute_trends(df, uid, aid, fh)  # Returns 0 if fails
```

### Pattern 3: Safe File Upload

```python
@app.post("/upload")
async def upload(request: Request, file: UploadFile):
    try:
        safe_filename = validate_filename(file.filename)
        # ... rest of upload ...
    except ValueError:
        log_policy_violation("bad_filename", detail=file.filename)
        raise HTTPException(400, "Invalid filename")
```

### Pattern 4: Create Artifact + Log

```python
# Create PDF
pdf_bytes = await generate_pdf(analysis_id, user_id)
export_path = EXPORTS_DIR / f"{export_id}.pdf"
export_path.write_bytes(pdf_bytes)

# Log metadata (Policy #11)
log_artifact_metadata(
    artifact_id=export_id,
    artifact_type="snapshot_pdf",
    user_id=user_id,
    analysis_id=analysis_id,
    file_hash=compute_file_hash(str(export_path))
)

db.create_export(...)
```

---

## Logging Output

### Success
```
✓ Route snapshot_analysis completed successfully
  request_id: a1b2c3d4, user_id: 5, analysis_id: 123, duration_ms: 245
```

### Violation
```
POLICY VIOLATION DETECTED: Cross-user analysis access denied
  request_id: b2c3d4e5, user_id: 3, analysis_id: 999
```

### Non-Fatal Failure
```
⚠ Operation trend_computation failed (non-fatal)
  request_id: c3d4e5f6, analysis_id: 123
```

---

## Policy Rules (POLICY.md Summary)

1. **Deterministic**: Same inputs → same outputs
2. **Single Source of Truth**: No duplicate logic
3. **Hard Isolation**: user_id boundary enforced
4. **Safe-Fail**: Errors degrade gracefully
5. **Auditability**: Everything is logged
6. **Local-First**: No Docker/cloud required
7. **No Spaghetti**: Layered architecture
8. **Auth**: Bcrypt + signed cookies
9. **Logging**: request_id + user_id + duration
10. **Testing**: Integration tests required
11. **Artifacts**: Metadata saved with PDFs
12. **Backups**: Daily backups
13. **AI-Safe**: AI is writer, not decider

---

## File Reference

| File | Purpose |
|------|---------|
| `core/policy.py` | Enforcement functions & decorators |
| `POLICY_INTEGRATION.md` | Full guide (examples, all functions) |
| `POLICY.md` | Engineering policy (rules & principles) |
| `app.py` | Add imports + decorators here |

---

## Run Policy Check at Startup

```python
from core.policy import print_policy_summary

if __name__ == "__main__":
    print_policy_summary()  # Shows all rules
    # ... start app ...
```

---

## Questions?

See `POLICY_INTEGRATION.md` for:
- Full function docs
- Code examples
- Test patterns
- Integration walkthrough
