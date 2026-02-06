"""
Financial calculations: KPIs, risk flags, shock scenarios.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Any

logger = logging.getLogger(__name__)


def compute_kpis(df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute key performance indicators from loan data.

    Args:
        df: Clean DataFrame with date, balance, rate columns

    Returns:
        Dict with 6 KPIs:
            - start_balance: First balance value
            - end_balance: Last balance value
            - pct_change: % change from start to end
            - avg_rate: Mean rate
            - rate_change: Last rate - First rate (in bps)
            - balance_stdev: Standard deviation of balance
    """
    start_bal = df["balance"].iloc[0]
    end_bal = df["balance"].iloc[-1]
    pct_change = ((end_bal - start_bal) / start_bal * 100) if start_bal != 0 else 0

    avg_rate = df["rate"].mean()
    start_rate = df["rate"].iloc[0]
    end_rate = df["rate"].iloc[-1]
    rate_change_bps = (end_rate - start_rate) * 10000  # Convert to basis points

    balance_stdev = df["balance"].std()

    kpis = {
        "start_balance": round(start_bal, 2),
        "end_balance": round(end_bal, 2),
        "pct_change": round(pct_change, 2),
        "avg_rate": round(avg_rate, 4),
        "rate_change_bps": round(rate_change_bps, 2),
        "balance_stdev": round(balance_stdev, 2),
    }

    logger.debug(f"KPIs computed: {kpis}")
    return kpis


def detect_flags(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detect risk flags in loan data.

    Args:
        df: Clean DataFrame

    Returns:
        Dict with flags:
            - volatility_spike: Bool, if stdev(balance) > 20% of mean
            - trend_change: Bool, if direction of balance changes
            - missing_dates: Bool, if gaps > 1 day exist
            - outliers: Count of outliers (IQR method on balance)
    """
    flags = {
        "volatility_spike": False,
        "trend_change": False,
        "missing_dates": False,
        "outlier_count": 0,
    }

    # Volatility spike
    mean_bal = df["balance"].mean()
    stdev_bal = df["balance"].std()
    if stdev_bal > 0.2 * mean_bal:
        flags["volatility_spike"] = True
        logger.info("Flag: Volatility spike detected")

    # Trend change
    balance_pct_changes = df["balance"].pct_change()
    if len(balance_pct_changes) > 1:
        signs = balance_pct_changes.dropna().apply(lambda x: 1 if x > 0 else -1)
        if len(signs) > 1:
            signs_reset = signs.reset_index(drop=True)
            if (signs_reset.iloc[:-1].values != signs_reset.iloc[1:].values).any():
                flags["trend_change"] = True
                logger.info("Flag: Trend change detected")

    # Missing dates
    date_diffs = df["date"].diff().dt.total_seconds() / 86400
    if (date_diffs > 1).any():
        flags["missing_dates"] = True
        logger.info("Flag: Missing dates detected")

    # Outliers (IQR method)
    Q1 = df["balance"].quantile(0.25)
    Q3 = df["balance"].quantile(0.75)
    IQR = Q3 - Q1
    outliers = (
        ((df["balance"] < Q1 - 1.5 * IQR) | (df["balance"] > Q3 + 1.5 * IQR))
        .sum()
    )
    flags["outlier_count"] = int(outliers)
    if outliers > 0:
        logger.info(f"Flag: {outliers} outliers detected")

    return flags


def compute_rate_shock(
    df: pd.DataFrame, shock_bps: int
) -> pd.DataFrame:
    """
    Apply basis point shock to rate column.

    Args:
        df: DataFrame with rate column
        shock_bps: Shock in basis points (positive or negative)

    Returns:
        DataFrame with new 'rate_shocked' column
    """
    df_shock = df.copy()
    df_shock["rate_shocked"] = df_shock["rate"] + (shock_bps / 10000)
    logger.info(f"Rate shock applied: {shock_bps} bps")
    return df_shock


def compute_balance_shock(
    df: pd.DataFrame, shock_pct: float
) -> pd.DataFrame:
    """
    Apply percentage shock to balance column.

    Args:
        df: DataFrame with balance column
        shock_pct: Shock as percentage (e.g., 5.0 for +5%, -5.0 for -5%)

    Returns:
        DataFrame with new 'balance_shocked' column
    """
    df_shock = df.copy()
    shock_multiplier = 1 + (shock_pct / 100)
    df_shock["balance_shocked"] = df_shock["balance"] * shock_multiplier
    logger.info(f"Balance shock applied: {shock_pct}%")
    return df_shock


def apply_shock_impact(
    df_baseline: pd.DataFrame, df_shocked: pd.DataFrame
) -> Dict[str, Any]:
    """
    Compare baseline vs shocked scenario and compute impact.

    Args:
        df_baseline: Original DataFrame
        df_shocked: Shocked DataFrame (with rate_shocked or balance_shocked)

    Returns:
        Dict with impact metrics:
            - end_balance_baseline, end_balance_shocked, impact_pct
            - avg_rate_baseline, avg_rate_shocked, impact_bps
    """
    impact = {}

    # Balance impact
    if "balance_shocked" in df_shocked.columns:
        baseline_end = df_baseline["balance"].iloc[-1]
        shocked_end = df_shocked["balance_shocked"].iloc[-1]
        impact["end_balance_baseline"] = round(baseline_end, 2)
        impact["end_balance_shocked"] = round(shocked_end, 2)
        impact["balance_impact_pct"] = round(
            ((shocked_end - baseline_end) / baseline_end * 100), 2
        )
        logger.debug(f"Balance impact: {impact['balance_impact_pct']}%")

    # Rate impact
    if "rate_shocked" in df_shocked.columns:
        baseline_rate = df_baseline["rate"].mean() * 10000
        shocked_rate = df_shocked["rate_shocked"].mean() * 10000
        impact["avg_rate_baseline_bps"] = round(baseline_rate, 2)
        impact["avg_rate_shocked_bps"] = round(shocked_rate, 2)
        impact["rate_impact_bps"] = round(shocked_rate - baseline_rate, 2)
        logger.debug(f"Rate impact: {impact['rate_impact_bps']} bps")

    return impact
