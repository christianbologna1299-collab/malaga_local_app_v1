"""
Scenario & Stress Simulator: apply shocks, compare results.
"""

import logging
from typing import Dict, Any, List
import pandas as pd
import plotly.graph_objects as go

from core.calculations import (
    compute_rate_shock,
    compute_balance_shock,
    apply_shock_impact,
)

logger = logging.getLogger(__name__)


def run_shocks(
    df: pd.DataFrame, rate_shocks_bps: List[int], balance_shocks_pct: List[float]
) -> Dict[str, Dict[str, Any]]:
    """
    Apply all shock scenarios and compute impacts.

    Args:
        df: Baseline DataFrame
        rate_shocks_bps: List of rate shocks in bps (e.g., [100, -100])
        balance_shocks_pct: List of balance shocks as % (e.g., [5, -5])

    Returns:
        Dict mapping scenario name to (shocked_df, impact_dict):
            "baseline": (df, {})
            "+100bps_rate": (df_shocked, impact)
            "-100bps_rate": (df_shocked, impact)
            "+5pct_balance": (df_shocked, impact)
            "-5pct_balance": (df_shocked, impact)
    """
    results = {
        "baseline": {
            "df": df.copy(),
            "impact": {},
        }
    }

    for shock_bps in rate_shocks_bps:
        df_shocked = compute_rate_shock(df, shock_bps)
        impact = apply_shock_impact(df, df_shocked)
        scenario_name = f"{shock_bps:+d}bps_rate"
        results[scenario_name] = {
            "df": df_shocked,
            "impact": impact,
        }
        logger.info(f"Shock scenario completed: {scenario_name}")

    for shock_pct in balance_shocks_pct:
        df_shocked = compute_balance_shock(df, shock_pct)
        impact = apply_shock_impact(df, df_shocked)
        scenario_name = f"{shock_pct:+.0f}pct_balance"
        results[scenario_name] = {
            "df": df_shocked,
            "impact": impact,
        }
        logger.info(f"Shock scenario completed: {scenario_name}")

    return results


def build_shock_comparison_chart(
    df_baseline: pd.DataFrame,
    df_shocked: pd.DataFrame,
    shock_label: str,
    column_baseline: str = "balance",
    column_shocked: str = "balance_shocked",
) -> go.Figure:
    """
    Build comparison chart (baseline vs shocked).

    Args:
        df_baseline: Baseline DataFrame
        df_shocked: Shocked DataFrame
        shock_label: Label for shocked trace (e.g., "+100 bps Rate Shock")
        column_baseline: Column to plot from baseline
        column_shocked: Column to plot from shocked

    Returns:
        Plotly Figure object (can be converted to HTML or PNG)
    """
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df_baseline["date"],
            y=df_baseline[column_baseline],
            mode="lines",
            name="Baseline",
            line=dict(color="#00D9FF", width=2),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Baseline: %{y:,.0f}<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_shocked["date"],
            y=df_shocked[column_shocked],
            mode="lines",
            name=shock_label,
            line=dict(color="#FF6B9D", width=2, dash="dash"),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Shocked: %{y:,.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        title=f"Scenario Comparison: {shock_label}",
        xaxis_title="Date",
        yaxis_title="Balance ($)" if column_baseline == "balance" else "Rate (%)",
        template="plotly_dark",
        height=450,
        hovermode="x unified",
        font=dict(color="#E0E0E0"),
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#0f0f1e",
        margin=dict(l=60, r=40, t=60, b=60),
    )
    fig.update_layout(xaxis=dict(showgrid=True, gridwidth=1, gridcolor="#333"))
    fig.update_layout(yaxis=dict(showgrid=True, gridwidth=1, gridcolor="#333"))

    logger.debug(f"Comparison chart generated: {shock_label}")
    return fig


def generate_impact_table_html(results: Dict[str, Dict[str, Any]]) -> str:
    """
    Generate HTML table showing impact summary for all scenarios.

    Args:
        results: Results dict from run_shocks()

    Returns:
        HTML string for impact table
    """
    html_parts = [
        """
    <table class="impact-table">
        <thead>
            <tr>
                <th>Scenario</th>
                <th>End Balance (Baseline)</th>
                <th>End Balance (Shocked)</th>
                <th>Impact (%)</th>
            </tr>
        </thead>
        <tbody>
    """
    ]

    for scenario, data in results.items():
        impact = data["impact"]
        if not impact:
            # Baseline scenario
            continue

        end_bal_baseline = impact.get("end_balance_baseline")
        end_bal_shocked = impact.get("end_balance_shocked")
        impact_pct = impact.get("balance_impact_pct")

        if end_bal_baseline and end_bal_shocked and impact_pct is not None:
            impact_class = "positive" if impact_pct > 0 else "negative" if impact_pct < 0 else "neutral"
            html_parts.append(
                f"""
            <tr>
                <td><strong>{scenario}</strong></td>
                <td>${end_bal_baseline:,.0f}</td>
                <td>${end_bal_shocked:,.0f}</td>
                <td class="{impact_class}">{impact_pct:+.2f}%</td>
            </tr>
            """
            )

    html_parts.append(
        """
        </tbody>
    </table>
    """
    )

    logger.debug("Impact table formatted")
    return "".join(html_parts)
