"""
Plain-Language Explain Engine: rule-based narrative generation.
Produces 3-section explainable output: What Matters, What Risks, What's Next.

M3.75: Extended to return rules_fired list for policy auditability.
"""

import logging
from typing import Dict, Any, List, Tuple
import pandas as pd

from core.calculations import compute_kpis, detect_flags

logger = logging.getLogger(__name__)


def generate_full_explanation(
    df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Generate complete 3-section explanation from loan data.

    Args:
        df: Clean DataFrame with date, balance, rate

    Returns:
        Dict with 4 keys:
            - what_matters: Key trends and patterns (HTML)
            - what_risks: Risk indicators and concerns (HTML)
            - whats_next: Recommendation for action (HTML)
            - rules_fired: List of rule names that produced output (M3.75)
    """
    kpis = compute_kpis(df)
    flags = detect_flags(df)

    what_matters, matters_rules = _generate_what_matters(df, kpis)
    what_risks, risks_rules = _generate_what_risks(df, kpis, flags)
    whats_next, next_rules = _generate_whats_next(df, kpis, flags)

    rules_fired = matters_rules + risks_rules + next_rules

    # M3.75: If no conditional rules fired, state neutral summary explicitly
    if not rules_fired:
        rules_fired.append("neutral_summary")

    logger.debug(f"Explain engine rules fired: {rules_fired}")

    return {
        "what_matters": what_matters,
        "what_risks": what_risks,
        "whats_next": whats_next,
        "rules_fired": rules_fired,
    }


def _generate_what_matters(df: pd.DataFrame, kpis: Dict[str, float]) -> Tuple[str, List[str]]:
    """
    Generate 'Here's what matters' section: key trends and major movements.

    Returns:
        Tuple of (html_string, list_of_rules_fired)
    """
    parts = []
    rules = []

    # Time span
    start_date = df["date"].min().strftime("%Y-%m-%d")
    end_date = df["date"].max().strftime("%Y-%m-%d")
    parts.append(
        f"<strong>Observation Period:</strong> {start_date} to {end_date} "
        f"({len(df)} data points)"
    )
    rules.append("observation_period")

    # Balance trend
    direction = "increased" if kpis["pct_change"] >= 0 else "decreased"
    parts.append(
        f"<strong>Balance Movement:</strong> The loan balance {direction} by "
        f"{abs(kpis['pct_change']):.2f}%, from ${kpis['start_balance']:,.0f} "
        f"to ${kpis['end_balance']:,.0f}."
    )
    rules.append("balance_movement")

    # Largest single change
    balance_changes = df["balance"].diff().dropna()
    if len(balance_changes) > 0:
        largest_change = balance_changes.abs().max()
        largest_idx = balance_changes.abs().idxmax()
        change_pct = (
            (balance_changes.iloc[largest_idx] / df["balance"].iloc[largest_idx])
            * 100
        )
        change_date = df["date"].iloc[largest_idx].strftime("%Y-%m-%d")
        parts.append(
            f"<strong>Largest Single Movement:</strong> ${largest_change:,.0f} "
            f"({change_pct:+.1f}%) on {change_date}."
        )
        rules.append("largest_movement")

    # Rate environment
    parts.append(
        f"<strong>Rate Environment:</strong> Average rate {kpis['avg_rate']*100:.2f}%, "
        f"with a net change of {kpis['rate_change_bps']:+.0f} basis points "
        f"over the period."
    )
    rules.append("rate_environment")

    html = "<ul><li>" + "</li><li>".join(parts) + "</li></ul>"
    logger.debug("'What Matters' section generated")
    return html, rules


def _generate_what_risks(
    df: pd.DataFrame, kpis: Dict[str, float], flags: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """
    Generate 'Here's the risk' section: potential concerns and anomalies.

    Returns:
        Tuple of (html_string, list_of_rules_fired)
    """
    parts = []
    rules = []

    # Volatility assessment
    volatility_pct = (kpis["balance_stdev"] / kpis["end_balance"] * 100) if kpis["end_balance"] != 0 else 0
    if volatility_pct > 10:
        parts.append(
            f"<strong>⚠️ High Balance Volatility:</strong> Standard deviation "
            f"is {volatility_pct:.1f}% of current balance (${kpis['balance_stdev']:,.0f}). "
            f"This suggests unpredictable fluctuations."
        )
        rules.append("high_volatility")
    else:
        parts.append(
            f"<strong>✓ Stable Balance:</strong> Volatility is {volatility_pct:.1f}% "
            f"of current balance—relatively predictable."
        )
        rules.append("stable_balance")

    # Trending risk
    if flags["trend_change"]:
        parts.append(
            "<strong>⚠️ Directional Changes:</strong> The balance exhibits multiple "
            "reversals (increases followed by decreases, or vice versa). "
            "This suggests changing business conditions or payment patterns."
        )
        rules.append("trend_change")
    else:
        parts.append(
            "<strong>✓ Consistent Trend:</strong> Balance moves in a single direction "
            "or is stable. Business conditions appear consistent."
        )
        rules.append("consistent_trend")

    # Data quality
    if flags["missing_dates"]:
        parts.append(
            f"<strong>⚠️ Data Gaps:</strong> {flags['outlier_count']} reporting gaps "
            "detected. Verify data completeness and reconciliation."
        )
        rules.append("data_gaps")

    if flags["outlier_count"] > 0:
        parts.append(
            f"<strong>⚠️ Statistical Outliers:</strong> {flags['outlier_count']} "
            "extreme values detected. These may represent special events (prepayment, "
            "restructuring, etc.) or data errors."
        )
        rules.append("statistical_outliers")

    # Rate risk
    rate_range = df["rate"].max() - df["rate"].min()
    rate_range_bps = rate_range * 10000
    if rate_range_bps > 50:
        parts.append(
            f"<strong>⚠️ Rate Volatility:</strong> Interest rates fluctuated by "
            f"{rate_range_bps:.0f} bps. This affects profitability and repricing risk."
        )
        rules.append("rate_volatility")

    if not parts:
        parts.append(
            "<strong>Overall Risk Level: Low</strong> No major anomalies or risks detected."
        )
        rules.append("low_risk_overall")

    html = "<ul><li>" + "</li><li>".join(parts) + "</li></ul>"
    logger.debug("'What Risks' section generated")
    return html, rules


def _generate_whats_next(
    df: pd.DataFrame, kpis: Dict[str, float], flags: Dict[str, Any]
) -> Tuple[str, List[str]]:
    """
    Generate 'Here's the best next move' section: actionable recommendations.

    Returns:
        Tuple of (html_string, list_of_rules_fired)
    """
    recommendations = []
    rules = []

    # Volatility-based recommendation
    if flags["volatility_spike"]:
        recommendations.append(
            "<strong>Investigate Balance Spikes:</strong> Consider root-cause analysis "
            "on the largest movements. Were they due to early payments, late charges, "
            "or system errors?"
        )
        rules.append("investigate_spikes")

    # Trend-based recommendation
    if flags["trend_change"]:
        recommendations.append(
            "<strong>Clarify Business Drivers:</strong> Interview borrower/portfolio "
            "team to understand why balance direction has changed. This may signal "
            "payment behavior shifts or external shocks."
        )
        rules.append("clarify_drivers")

    # Data quality
    if flags["missing_dates"]:
        recommendations.append(
            "<strong>Reconcile Data Gaps:</strong> Ensure all reporting periods are "
            "captured. Missing dates can distort trend analysis."
        )
        rules.append("reconcile_gaps")

    # Rate environment
    if kpis["rate_change_bps"] != 0:
        direction = "fallen" if kpis["rate_change_bps"] < 0 else "risen"
        recommendations.append(
            f"<strong>Monitor Rate Repricing:</strong> Rates have {direction}. "
            "Review repricing schedules and consider hedging strategies if exposed."
        )
        rules.append("monitor_repricing")

    # Default recommendation
    if not recommendations:
        recommendations.append(
            "<strong>Continue Standard Monitoring:</strong> Loan appears stable. "
            "Maintain regular review cycles to detect early warning signs."
        )
        rules.append("standard_monitoring")

    # Add forward-looking recommendation
    recommendations.append(
        "<strong>Run Stress Tests:</strong> Use the Scenario & Stress Simulator "
        "to model impacts of rate shocks or balance shifts."
    )
    rules.append("run_stress_tests")

    html = "<ul><li>" + "</li><li>".join(recommendations) + "</li></ul>"
    logger.debug("'What's Next' section generated")
    return html, rules
