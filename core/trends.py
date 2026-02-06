"""
Trend Engine v1.0 - Deterministic Trend Analysis
Bank-grade trend computation with versioning and determinism guarantees.
"""

import logging
import hashlib
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================================
# TREND ENGINE CONSTANTS (Versioning + Determinism Contract)
# ============================================================================

TREND_ENGINE_VERSION = "v1.0"
TREND_WINDOWS = [30, 90, 180]  # days
TREND_SERIES = ["balance", "rate"]  # series names to analyze

# Minimum sample size for valid trend (prevents noise on small datasets)
MIN_SAMPLE_SIZE = 5

# Outlier detection: coefficient of variation threshold
OUTLIER_CV_THRESHOLD = 3.0


# ============================================================================
# DATA MODELS (Deterministic Result Types)
# ============================================================================

@dataclass
class TrendResult:
    """
    Single trend metric result for one window × one series.
    Bank-grade deterministic structure.
    """
    user_id: int
    analysis_id: int
    window_days: int
    series_name: str
    slope_per_day: float
    direction: str  # "up" | "down" | "flat"
    strength_score: float  # [0.0, 1.0]
    volatility: float
    confidence: str  # "high" | "medium" | "low"
    sample_size: int
    data_quality: Dict[str, Any]  # {"missing_dates": int, "duplicate_dates": int, "outlier_count": int}
    breakpoint_dates: List[str]  # ISO format ["2024-01-15", ...]
    inputs_hash: str  # Determinism key: hash(file_hash + version + window + series)
    trend_engine_version: str

    def to_metrics_json(self) -> str:
        """Convert to compact JSON for DB storage (metrics_json column)."""
        import json
        metrics = {
            "slope_per_day": round(self.slope_per_day, 6),
            "direction": self.direction,
            "strength_score": round(self.strength_score, 3),
            "volatility": round(self.volatility, 4),
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "data_quality": self.data_quality,
            "breakpoint_dates": self.breakpoint_dates,
            "trend_engine_version": self.trend_engine_version,
        }
        return json.dumps(metrics)


# ============================================================================
# HASHING & DETERMINISM (Inputs Hash Contract)
# ============================================================================

def compute_inputs_hash(file_hash: str, window_days: int, series_name: str) -> str:
    """
    Compute deterministic inputs hash.
    Used to avoid recomputing same trend twice.

    Hash = SHA256(file_hash + TREND_ENGINE_VERSION + window_days + series_name)

    Args:
        file_hash: SHA256 hash of the source parquet file
        window_days: Window size (30/90/180)
        series_name: Series name ("balance" or "rate")

    Returns:
        Deterministic hash string
    """
    combined = f"{file_hash}{TREND_ENGINE_VERSION}{window_days}{series_name}"
    return hashlib.sha256(combined.encode()).hexdigest()


# ============================================================================
# TREND COMPUTATION (Core Engine)
# ============================================================================

def compute_slope(series: np.ndarray) -> float:
    """
    Compute linear slope (per day) using least-squares regression.

    Args:
        series: 1D numpy array of values

    Returns:
        Slope per day
    """
    if len(series) < 2:
        return 0.0

    x = np.arange(len(series))
    coeffs = np.polyfit(x, series, 1)
    return float(coeffs[0])


def compute_volatility(series: np.ndarray) -> float:
    """
    Compute volatility as coefficient of variation (std / mean).
    Handles edge cases (zero mean, single value).

    Args:
        series: 1D numpy array of values

    Returns:
        Coefficient of variation (dimensionless)
    """
    if len(series) < 2:
        return 0.0

    mean = np.mean(series)
    if abs(mean) < 1e-10:  # Avoid division by zero
        # Use absolute range as fallback
        return float(np.std(series)) if np.std(series) > 0 else 0.0

    return float(np.std(series) / abs(mean))


def detect_outliers(series: np.ndarray, threshold: float = OUTLIER_CV_THRESHOLD) -> Tuple[np.ndarray, int]:
    """
    Detect outliers using modified Z-score (Hampel method).

    Args:
        series: 1D numpy array
        threshold: Z-score threshold (default 3.0)

    Returns:
        Tuple of (clean_series, outlier_count)
    """
    if len(series) < 3:
        return series, 0

    # Compute median and MAD (median absolute deviation)
    median = np.median(series)
    mad = np.median(np.abs(series - median))

    if mad < 1e-10:
        # All values close to median; no outliers detected
        return series, 0

    # Modified Z-score
    z_scores = 0.6745 * (series - median) / mad
    outliers = np.abs(z_scores) > threshold
    outlier_count = int(np.sum(outliers))

    # For trend detection, keep outliers but track them
    return series, outlier_count


def detect_breakpoints(series: np.ndarray, window: int = 7) -> List[int]:
    """
    Detect breakpoints (structural breaks) using simple rolling std.
    Light heuristic: flag indices where rolling std exceeds 2x median rolling std.

    Args:
        series: 1D numpy array
        window: Rolling window size (days)

    Returns:
        List of indices where breakpoints occur
    """
    if len(series) < window + 1:
        return []

    rolling_std = pd.Series(series).rolling(window=window).std().values
    rolling_std_clean = rolling_std[~np.isnan(rolling_std)]

    if len(rolling_std_clean) == 0:
        return []

    threshold = 2.0 * np.median(rolling_std_clean)
    breakpoints = np.where(rolling_std > threshold)[0].tolist()

    return breakpoints


def score_confidence(
    sample_size: int,
    volatility: float,
    outlier_count: int,
    missing_count: int
) -> str:
    """
    Assign confidence level based on data quality indicators.
    Conservative scoring: favor "medium" and "low" over "high".

    Args:
        sample_size: Number of data points
        volatility: Coefficient of variation
        outlier_count: Number of detected outliers
        missing_count: Number of missing dates in window

    Returns:
        "high" | "medium" | "low"
    """
    # Start with "medium" as default
    confidence = "medium"

    # Downgrade if sample too small
    if sample_size < 10:
        return "low"

    # Downgrade if high volatility
    if volatility > 0.5:
        confidence = "low"

    # Downgrade if many outliers (>10% of sample)
    if outlier_count > sample_size * 0.1:
        confidence = "low"

    # Downgrade if many missing dates (>20% of window)
    expected_dates = sample_size + missing_count
    if expected_dates > 0 and missing_count / expected_dates > 0.2:
        confidence = "low"

    # Upgrade to "high" only if very good quality
    if (sample_size >= 50 and
        volatility < 0.2 and
        outlier_count == 0 and
        missing_count == 0):
        confidence = "high"

    return confidence


def compute_trend_for_series(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    window_days: int,
    user_id: int,
    analysis_id: int,
    file_hash: str,
    series_name: str
) -> TrendResult:
    """
    Compute trend metrics for one series over a rolling window.

    Args:
        df: DataFrame with at least date_col and value_col
        date_col: Column name for dates (must be datetime-like)
        value_col: Column name for values
        window_days: Window size (30/90/180)
        user_id: User ID (for result tagging)
        analysis_id: Analysis ID (for result tagging)
        file_hash: File hash (for inputs_hash computation)
        series_name: Series name ("balance" or "rate")

    Returns:
        TrendResult object
    """
    # Ensure date column is datetime
    if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col])

    # Filter to last window_days
    cutoff_date = df[date_col].max() - pd.Timedelta(days=window_days)
    windowed = df[df[date_col] >= cutoff_date].copy()

    sample_size = len(windowed)

    # Handle small datasets
    if sample_size < MIN_SAMPLE_SIZE:
        return TrendResult(
            user_id=user_id,
            analysis_id=analysis_id,
            window_days=window_days,
            series_name=series_name,
            slope_per_day=0.0,
            direction="flat",
            strength_score=0.0,
            volatility=0.0,
            confidence="low",
            sample_size=sample_size,
            data_quality={
                "missing_dates": 0,
                "duplicate_dates": 0,
                "outlier_count": 0
            },
            breakpoint_dates=[],
            inputs_hash=compute_inputs_hash(file_hash, window_days, series_name),
            trend_engine_version=TREND_ENGINE_VERSION
        )

    # Extract value series
    values = windowed[value_col].values.astype(float)

    # Skip NaN values
    valid_mask = ~np.isnan(values)
    values_clean = values[valid_mask]
    dates_clean = windowed[date_col].values[valid_mask]

    # Data quality metrics
    missing_count = int(np.sum(~valid_mask))
    duplicate_dates = len(dates_clean) - len(set(dates_clean))

    # Outlier detection
    values_clean_arr = np.array(values_clean)
    _, outlier_count = detect_outliers(values_clean_arr)

    # Core trend metrics
    slope = compute_slope(values_clean_arr)
    volatility = compute_volatility(values_clean_arr)

    # Direction and strength
    direction = "up" if slope > 1e-6 else ("down" if slope < -1e-6 else "flat")

    # Strength score: normalized abs(slope) / (1 + volatility)
    # Normalized to [0, 1] scale
    strength_score = min(1.0, abs(slope) / (1.0 + volatility)) if abs(slope) > 0 else 0.0

    # Confidence level
    confidence = score_confidence(sample_size, volatility, outlier_count, missing_count)

    # Breakpoints
    breakpoint_indices = detect_breakpoints(values_clean_arr, window=7)
    breakpoint_dates = [
        pd.Timestamp(dates_clean[idx]).isoformat()
        for idx in breakpoint_indices
        if idx < len(dates_clean)
    ]

    return TrendResult(
        user_id=user_id,
        analysis_id=analysis_id,
        window_days=window_days,
        series_name=series_name,
        slope_per_day=slope,
        direction=direction,
        strength_score=strength_score,
        volatility=volatility,
        confidence=confidence,
        sample_size=sample_size,
        data_quality={
            "missing_dates": missing_count,
            "duplicate_dates": duplicate_dates,
            "outlier_count": outlier_count
        },
        breakpoint_dates=breakpoint_dates,
        inputs_hash=compute_inputs_hash(file_hash, window_days, series_name),
        trend_engine_version=TREND_ENGINE_VERSION
    )


def compute_trends(
    df: pd.DataFrame,
    date_col: str = "date",
    balance_col: str = "balance",
    rate_col: str = "rate",
    user_id: int = None,
    analysis_id: int = None,
    file_hash: str = None,
    windows: List[int] = None,
    series: List[str] = None
) -> List[TrendResult]:
    """
    Main entry point: compute all trends for a dataset.

    Computes trends for each series × each window.
    Returns list of TrendResult objects.

    Args:
        df: Input DataFrame (must have date_col, balance_col, rate_col)
        date_col: Name of date column (default "date")
        balance_col: Name of balance column (default "balance")
        rate_col: Name of rate column (default "rate")
        user_id: User ID (required)
        analysis_id: Analysis ID (required)
        file_hash: File hash (required for determinism)
        windows: List of window sizes (default TREND_WINDOWS)
        series: List of series to analyze (default TREND_SERIES)

    Returns:
        List of TrendResult objects (length = len(windows) × len(series))
    """
    if windows is None:
        windows = TREND_WINDOWS
    if series is None:
        series = TREND_SERIES

    if user_id is None or analysis_id is None or file_hash is None:
        logger.warning("compute_trends called without required user_id, analysis_id, or file_hash")
        return []

    if df.empty:
        logger.warning("compute_trends: DataFrame is empty")
        return []

    # Verify required columns
    required_cols = [date_col]
    if "balance" in series:
        required_cols.append(balance_col)
    if "rate" in series:
        required_cols.append(rate_col)

    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logger.error(f"compute_trends: Missing columns {missing_cols}")
        return []

    results = []

    # Compute trends for each series × window
    for series_name in series:
        if series_name == "balance":
            value_col = balance_col
        elif series_name == "rate":
            value_col = rate_col
        else:
            logger.warning(f"Unknown series: {series_name}, skipping")
            continue

        if value_col not in df.columns:
            logger.warning(f"Column {value_col} not found, skipping series {series_name}")
            continue

        for window_days in windows:
            try:
                result = compute_trend_for_series(
                    df=df,
                    date_col=date_col,
                    value_col=value_col,
                    window_days=window_days,
                    user_id=user_id,
                    analysis_id=analysis_id,
                    file_hash=file_hash,
                    series_name=series_name
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Error computing trend for {series_name} window {window_days}: {e}")
                continue

    logger.info(f"Computed {len(results)} trends for analysis {analysis_id}")
    return results
