#!/usr/bin/env python3
"""
M3.75 Smoke Test — verifies policy, audit, and explain integrity.
Usage: python scripts/smoke_m375.py
Exit code 0 = PASS, nonzero = FAIL
"""

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASSED = 0
FAILED = 0


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name} — {detail}")


def main():
    print("=" * 60)
    print("M3.75 Smoke Tests")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Core imports
    # ------------------------------------------------------------------
    print("\n[1] Core imports")
    try:
        from core.policy import (
            PolicyConfig,
            PolicyViolation,
            policy_guard,
            ensure_audit_events_table,
            policy_log_event,
            policy_config,
        )
        check("core.policy imports", True)
    except ImportError as e:
        check("core.policy imports", False, str(e))
        print("\nCannot continue without core.policy. Aborting.")
        sys.exit(1)

    try:
        import app as app_module
        check("app.py imports", True)
    except Exception as e:
        check("app.py imports", False, str(e))
        print("\nCannot continue without app.py. Aborting.")
        sys.exit(1)

    try:
        from features.explain_engine import generate_full_explanation
        check("explain_engine imports", True)
    except ImportError as e:
        check("explain_engine imports", False, str(e))

    # ------------------------------------------------------------------
    # 2. PolicyConfig
    # ------------------------------------------------------------------
    print("\n[2] PolicyConfig")
    cfg = PolicyConfig()
    check("PolicyConfig instantiates", cfg is not None)
    check("LOCAL_FIRST_ONLY default True", cfg.LOCAL_FIRST_ONLY is True)
    check("REQUIRE_ANALYSIS_OWNERSHIP default True", cfg.REQUIRE_ANALYSIS_OWNERSHIP is True)

    # ------------------------------------------------------------------
    # 3. PolicyViolation
    # ------------------------------------------------------------------
    print("\n[3] PolicyViolation")
    exc = PolicyViolation(rule="TEST", detail="smoke test")
    check("PolicyViolation instantiates", exc.rule == "TEST")
    check("PolicyViolation is Exception", isinstance(exc, Exception))

    # ------------------------------------------------------------------
    # 4. policy_guard pass/reject
    # ------------------------------------------------------------------
    print("\n[4] policy_guard")
    try:
        policy_guard({"route": "/test", "mode": "session"})
        check("policy_guard passes session mode", True)
    except PolicyViolation:
        check("policy_guard passes session mode", False, "unexpected violation")

    try:
        policy_guard({"route": "/test", "mode": "persistent", "user_id": None})
        check("policy_guard rejects persistent without user", False, "should have raised")
    except PolicyViolation:
        check("policy_guard rejects persistent without user", True)

    try:
        policy_guard({"route": "/test", "mode": "session", "nan_fields": ["balance"]})
        check("policy_guard rejects NaN fields", False, "should have raised")
    except PolicyViolation:
        check("policy_guard rejects NaN fields", True)

    # ------------------------------------------------------------------
    # 5. audit_events table
    # ------------------------------------------------------------------
    print("\n[5] audit_events table")
    import sqlite3
    conn = sqlite3.connect(":memory:")
    ok = ensure_audit_events_table(conn)
    check("audit_events table created in-memory", ok is True)

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'")
    check("audit_events table exists", cursor.fetchone() is not None)
    conn.close()

    # ------------------------------------------------------------------
    # 6. Explain engine rules_fired
    # ------------------------------------------------------------------
    print("\n[6] Explain engine rules_fired")
    try:
        import pandas as pd
        import numpy as np
        dates = pd.date_range("2024-01-01", periods=12, freq="MS")
        df = pd.DataFrame({
            "date": dates,
            "balance": np.linspace(100000, 95000, 12),
            "rate": np.linspace(0.045, 0.05, 12),
        })
        result = generate_full_explanation(df)
        check("generate_full_explanation returns dict", isinstance(result, dict))
        check("rules_fired key exists", "rules_fired" in result)
        check("rules_fired is list", isinstance(result.get("rules_fired"), list))
        check("rules_fired is non-empty", len(result.get("rules_fired", [])) > 0,
              f"got {result.get('rules_fired')}")
        check("what_matters key exists", "what_matters" in result)
        check("what_risks key exists", "what_risks" in result)
        check("whats_next key exists", "whats_next" in result)
    except Exception as e:
        check("explain engine test", False, str(e))

    # ------------------------------------------------------------------
    # 7. App helpers (Phase B)
    # ------------------------------------------------------------------
    print("\n[7] App helpers (Phase B)")
    try:
        from app import get_client_ip, safe_json_dumps
        check("get_client_ip importable", True)
        check("safe_json_dumps importable", True)

        import datetime
        result = safe_json_dumps({"ts": datetime.datetime.now()})
        check("safe_json_dumps handles datetime", '"ts"' in result)

        result = safe_json_dumps({"val": float("nan")})
        check("safe_json_dumps handles NaN", isinstance(result, str))
    except Exception as e:
        check("app helpers", False, str(e))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    total = PASSED + FAILED
    print(f"Results: {PASSED}/{total} passed, {FAILED} failed")
    if FAILED == 0:
        print("M3.75 SMOKE TESTS: ALL PASSED")
    else:
        print("M3.75 SMOKE TESTS: FAILURES DETECTED")
    print("=" * 60)

    sys.exit(1 if FAILED > 0 else 0)


if __name__ == "__main__":
    main()
