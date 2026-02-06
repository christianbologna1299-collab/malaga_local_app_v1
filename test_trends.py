#!/usr/bin/env python
"""
Trend Engine v1.0 Test Suite
Tests for deterministic trend analysis with versioning and caching.
"""
import sys
import os
import json
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.trends import (
    compute_trends,
    compute_slope,
    compute_volatility,
    detect_outliers,
    score_confidence,
    compute_inputs_hash,
    TrendResult,
    TREND_ENGINE_VERSION,
    TREND_WINDOWS,
    TREND_SERIES,
)
from core.db import Database

print("=" * 70)
print("TREND ENGINE V1.0 TEST SUITE")
print("=" * 70)

# Initialize test database
TEST_DB_PATH = "test_trends.db"
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

db = Database(db_path=TEST_DB_PATH)
print(f"\n✓ Test database initialized: {TEST_DB_PATH}")

# ============================================================================
# TEST 1: Slope Computation (Deterministic)
# ============================================================================
print("\n[TEST 1] Slope Computation...")
try:
    # Uptrend: +1 per day
    uptrend = np.array([100 + i for i in range(10)])
    slope_up = compute_slope(uptrend)
    assert slope_up > 0.9, f"Expected positive slope, got {slope_up}"

    # Downtrend: -1 per day
    downtrend = np.array([100 - i for i in range(10)])
    slope_down = compute_slope(downtrend)
    assert slope_down < -0.9, f"Expected negative slope, got {slope_down}"

    # Flat: minimize slope
    flat = np.array([100] * 10)
    slope_flat = compute_slope(flat)
    assert abs(slope_flat) < 0.1, f"Expected flat slope, got {slope_flat}"

    print("  ✓ Slope uptrend detected correctly")
    print("  ✓ Slope downtrend detected correctly")
    print("  ✓ Slope flat trend detected correctly")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 2: Volatility Computation
# ============================================================================
print("\n[TEST 2] Volatility Computation...")
try:
    # Low volatility
    low_vol = np.array([100, 101, 100, 101, 100])
    vol_low = compute_volatility(low_vol)
    assert vol_low < 0.1, f"Expected low volatility, got {vol_low}"

    # High volatility
    high_vol = np.array([50, 150, 50, 150, 50])
    vol_high = compute_volatility(high_vol)
    assert vol_high > 0.5, f"Expected high volatility, got {vol_high}"

    # Edge case: flat data (zero mean)
    zero_mean = np.array([-1, 0, 1, -1, 0, 1])
    vol_zero = compute_volatility(zero_mean)
    assert vol_zero >= 0, f"Expected non-negative volatility, got {vol_zero}"

    print("  ✓ Low volatility measured correctly")
    print("  ✓ High volatility measured correctly")
    print("  ✓ Edge case (zero mean) handled correctly")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 3: Outlier Detection
# ============================================================================
print("\n[TEST 3] Outlier Detection...")
try:
    # Series with significant outlier
    series_with_outlier = np.array([100, 101, 102, 101, 100, 500, 101, 100])
    clean_series, outlier_count = detect_outliers(series_with_outlier, threshold=3.0)
    assert outlier_count > 0, f"Expected outliers to be detected, got {outlier_count}"

    # Series without outliers
    clean_series = np.array([100, 101, 102, 101, 100, 99, 101, 100])
    clean_series_arr, outlier_count_clean = detect_outliers(clean_series, threshold=3.0)
    assert outlier_count_clean == 0, f"Expected no outliers, got {outlier_count_clean}"

    print("  ✓ Outliers detected correctly")
    print("  ✓ Clean series validated correctly")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 4: Confidence Scoring
# ============================================================================
print("\n[TEST 4] Confidence Scoring...")
try:
    # High confidence: large sample, low volatility, no outliers
    conf_high = score_confidence(
        sample_size=100,
        volatility=0.1,
        outlier_count=0,
        missing_count=0
    )
    assert conf_high == "high", f"Expected 'high' confidence, got '{conf_high}'"

    # Medium confidence: moderate sample
    conf_med = score_confidence(
        sample_size=20,
        volatility=0.3,
        outlier_count=1,
        missing_count=2
    )
    assert conf_med in ["medium", "low"], f"Expected 'medium' or 'low' confidence, got '{conf_med}'"

    # Low confidence: small sample
    conf_low = score_confidence(
        sample_size=3,
        volatility=0.1,
        outlier_count=0,
        missing_count=0
    )
    assert conf_low == "low", f"Expected 'low' confidence, got '{conf_low}'"

    print("  ✓ High confidence scored correctly")
    print("  ✓ Medium confidence scored correctly")
    print("  ✓ Low confidence scored correctly")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 5: Deterministic Hashing
# ============================================================================
print("\n[TEST 5] Deterministic Hashing (Caching Contract)...")
try:
    file_hash = "abc123def456"
    window = 30
    series = "balance"

    # Same inputs → same hash
    hash1 = compute_inputs_hash(file_hash, window, series)
    hash2 = compute_inputs_hash(file_hash, window, series)
    assert hash1 == hash2, f"Hashes should be identical: {hash1} != {hash2}"

    # Different inputs → different hash
    hash3 = compute_inputs_hash(file_hash, 90, series)
    assert hash1 != hash3, f"Different windows should produce different hashes"

    # Different series → different hash
    hash4 = compute_inputs_hash(file_hash, window, "rate")
    assert hash1 != hash4, f"Different series should produce different hashes"

    print("  ✓ Deterministic hashing produces consistent results")
    print("  ✓ Different inputs produce different hashes")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 6: Trend Result Serialization
# ============================================================================
print("\n[TEST 6] Trend Result Serialization (JSON)...")
try:
    result = TrendResult(
        user_id=1,
        analysis_id=1,
        window_days=30,
        series_name="balance",
        slope_per_day=0.123456,
        direction="up",
        strength_score=0.75,
        volatility=0.25,
        confidence="high",
        sample_size=50,
        data_quality={"missing_dates": 0, "duplicate_dates": 0, "outlier_count": 1},
        breakpoint_dates=["2024-01-15", "2024-02-01"],
        inputs_hash="testhash123",
        trend_engine_version="v1.0"
    )

    metrics_json = result.to_metrics_json()
    metrics = json.loads(metrics_json)

    assert metrics["direction"] == "up", "Direction not serialized correctly"
    assert metrics["confidence"] == "high", "Confidence not serialized correctly"
    assert metrics["sample_size"] == 50, "Sample size not serialized correctly"
    assert len(metrics["breakpoint_dates"]) == 2, "Breakpoint dates not serialized correctly"

    print("  ✓ TrendResult serializes to JSON correctly")
    print("  ✓ Metrics JSON is valid and complete")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 7: Trend Computation (Integration)
# ============================================================================
print("\n[TEST 7] Trend Computation Integration...")
try:
    # Create test DataFrame with uptrend balance and downtrend rate
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    df = pd.DataFrame({
        'date': dates,
        'balance': 100000 + np.arange(100) * 100,  # Steady uptrend
        'rate': 5.0 - np.arange(100) * 0.01,  # Steady downtrend
    })

    user_id = 1
    analysis_id = 1
    file_hash = "test_file_hash_123"

    trends = compute_trends(
        df=df,
        date_col="date",
        balance_col="balance",
        rate_col="rate",
        user_id=user_id,
        analysis_id=analysis_id,
        file_hash=file_hash,
        windows=[30, 90],
        series=["balance", "rate"]
    )

    # Should produce 4 trends: 2 windows × 2 series
    assert len(trends) == 4, f"Expected 4 trends, got {len(trends)}"

    # Check balance trend (should be UP)
    balance_90 = [t for t in trends if t.series_name == "balance" and t.window_days == 90][0]
    assert balance_90.direction == "up", f"Balance should trend up, got {balance_90.direction}"

    # Check rate trend (should be DOWN)
    rate_90 = [t for t in trends if t.series_name == "rate" and t.window_days == 90][0]
    assert rate_90.direction == "down", f"Rate should trend down, got {rate_90.direction}"

    # Check confidence is reasonable
    assert balance_90.confidence in ["high", "medium", "low"], f"Invalid confidence: {balance_90.confidence}"
    assert balance_90.sample_size >= 30, f"Sample size too small: {balance_90.sample_size}"

    print("  ✓ Trends computed for all windows and series")
    print("  ✓ Balance uptrend detected correctly")
    print("  ✓ Rate downtrend detected correctly")
    print("  ✓ Confidence score is reasonable")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 8: Trend Persistence (DB CRUD)
# ============================================================================
print("\n[TEST 8] Trend Persistence (Database)...")
try:
    # Create test user
    user_id = db.create_user("trend_test_user", "hashed_password_12345")
    assert user_id is not None, "Failed to create test user"

    # Create test analysis
    analysis_id = db.create_analysis(
        user_id=user_id,
        filename="trend_test.csv",
        row_count=100,
        date_min="2024-01-01",
        date_max="2024-04-09"
    )
    assert analysis_id is not None, "Failed to create test analysis"

    # Create trend record
    inputs_hash = "test_trend_hash_001"
    trend_id = db.create_trend(
        user_id=user_id,
        analysis_id=analysis_id,
        window_days=30,
        series_name="balance",
        metrics_json='{"slope_per_day": 100.5, "direction": "up"}',
        confidence="high",
        inputs_hash=inputs_hash,
        trend_engine_version="v1.0"
    )
    assert trend_id is not None, "Failed to create trend record"

    # Verify trend exists
    exists = db.trend_exists(inputs_hash)
    assert exists, "Trend should exist after creation"

    # List trends for analysis
    trends_list = db.list_trends_for_analysis(analysis_id, user_id)
    assert len(trends_list) > 0, "Failed to list trends"
    assert trends_list[0]["series_name"] == "balance", "Trend not retrieved correctly"

    print("  ✓ Trend created successfully")
    print("  ✓ Trend existence verified")
    print("  ✓ Trend listed correctly")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 9: Determinism Caching (No Duplicate Trends)
# ============================================================================
print("\n[TEST 9] Determinism Caching (No Duplicates)...")
try:
    user_id = db.create_user("cache_test_user", "hashed_password_12345")
    analysis_id = db.create_analysis(
        user_id=user_id,
        filename="cache_test.csv",
        row_count=100
    )

    inputs_hash = "test_cache_hash_002"

    # First trend creation
    trend_id_1 = db.create_trend(
        user_id=user_id,
        analysis_id=analysis_id,
        window_days=30,
        series_name="balance",
        metrics_json='{"slope_per_day": 50.0}',
        confidence="high",
        inputs_hash=inputs_hash,
        trend_engine_version="v1.0"
    )
    assert trend_id_1 is not None, "First trend creation failed"

    # Second creation with same inputs_hash (should return None due to unique constraint)
    trend_id_2 = db.create_trend(
        user_id=user_id,
        analysis_id=analysis_id,
        window_days=30,
        series_name="balance",
        metrics_json='{"slope_per_day": 50.0}',
        confidence="high",
        inputs_hash=inputs_hash,
        trend_engine_version="v1.0"
    )
    assert trend_id_2 is None, "Duplicate trend should not be created"

    # Verify only one trend exists with this inputs_hash
    trends = db.execute_query(
        "SELECT COUNT(*) as cnt FROM analysis_trends WHERE inputs_hash = ?",
        (inputs_hash,),
        fetch="one"
    )
    assert trends["cnt"] == 1, f"Expected 1 trend, got {trends['cnt']}"

    print("  ✓ Determinism caching prevents duplicate trends")
    print("  ✓ Unique constraint enforced on inputs_hash")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 10: User Isolation
# ============================================================================
print("\n[TEST 10] User Isolation (Multi-User)...")
try:
    # Create two users
    user_a = db.create_user("user_a_trend", "password_a")
    user_b = db.create_user("user_b_trend", "password_b")
    assert user_a is not None and user_b is not None, "Failed to create users"

    # Create analyses for each user
    analysis_a = db.create_analysis(
        user_id=user_a,
        filename="user_a_data.csv",
        row_count=50
    )
    analysis_b = db.create_analysis(
        user_id=user_b,
        filename="user_b_data.csv",
        row_count=75
    )

    # Create trends for each analysis
    db.create_trend(
        user_id=user_a,
        analysis_id=analysis_a,
        window_days=30,
        series_name="balance",
        metrics_json='{"direction": "up"}',
        confidence="high",
        inputs_hash="user_a_trend_hash",
        trend_engine_version="v1.0"
    )
    db.create_trend(
        user_id=user_b,
        analysis_id=analysis_b,
        window_days=30,
        series_name="balance",
        metrics_json='{"direction": "down"}',
        confidence="medium",
        inputs_hash="user_b_trend_hash",
        trend_engine_version="v1.0"
    )

    # User A should only see their own trends
    trends_a = db.list_trends_for_analysis(analysis_a, user_a)
    assert len(trends_a) == 1, f"User A should see 1 trend, got {len(trends_a)}"
    assert trends_a[0]["confidence"] == "high", "User A's trend has wrong confidence"

    # User B should not see User A's trends
    trends_a_from_b = db.list_trends_for_analysis(analysis_a, user_b)
    assert len(trends_a_from_b) == 0, f"User B should not see User A's trends"

    # User B should only see their own trends
    trends_b = db.list_trends_for_analysis(analysis_b, user_b)
    assert len(trends_b) == 1, f"User B should see 1 trend, got {len(trends_b)}"
    assert trends_b[0]["confidence"] == "medium", "User B's trend has wrong confidence"

    print("  ✓ Users isolated: User A sees only their trends")
    print("  ✓ Users isolated: User B sees only their trends")
    print("  ✓ Cross-user access prevented")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# TEST 11: Graceful Handling of Small Datasets
# ============================================================================
print("\n[TEST 11] Graceful Handling of Small Datasets...")
try:
    # Create DataFrame with very few rows
    small_df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=3),
        'balance': [100, 105, 110],
        'rate': [5.0, 4.9, 4.8]
    })

    trends_small = compute_trends(
        df=small_df,
        date_col="date",
        balance_col="balance",
        rate_col="rate",
        user_id=1,
        analysis_id=1,
        file_hash="small_test_hash",
        windows=[30, 90],
        series=["balance", "rate"]
    )

    # Should still produce trends, but confidence should be "low"
    assert len(trends_small) > 0, "Trends should be computed even for small datasets"
    for trend in trends_small:
        assert trend.confidence == "low", f"Small dataset trend should have low confidence, got {trend.confidence}"
        assert trend.sample_size <= 3, f"Sample size should be <= 3, got {trend.sample_size}"

    print("  ✓ Small datasets handled gracefully")
    print("  ✓ Confidence correctly marked as low for small samples")
except AssertionError as e:
    print(f"  ✗ FAILED: {e}")
    sys.exit(1)

# ============================================================================
# Cleanup
# ============================================================================
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)
    print(f"\n✓ Test database cleaned up")

print("\n" + "=" * 70)
print("ALL TREND ENGINE TESTS PASSED ✓")
print("=" * 70)
