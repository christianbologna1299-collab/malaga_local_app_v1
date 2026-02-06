"""
Borrower Snapshot feature: charts, KPI tiles, flags, narrative.
"""

import logging
from typing import Dict, Any, Tuple
import pandas as pd
import plotly.graph_objects as go

from core.calculations import compute_kpis, detect_flags

logger = logging.getLogger(__name__)


def build_balance_chart(df: pd.DataFrame) -> go.Figure:
    """
    Build interactive balance over time Plotly chart.

    Args:
        df: DataFrame with date and balance columns

    Returns:
        Plotly Figure object (can be converted to HTML or PNG)
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["balance"],
            mode="lines+markers",
            name="Balance",
            line=dict(color="#00D9FF", width=2),
            marker=dict(size=5, color="#00D9FF"),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Balance: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Balance Over Time",
        xaxis_title="Date",
        yaxis_title="Balance ($)",
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

    logger.debug("Balance chart generated")
    return fig


def build_rate_chart(df: pd.DataFrame) -> go.Figure:
    """
    Build interactive rate over time Plotly chart.

    Args:
        df: DataFrame with date and rate columns

    Returns:
        Plotly Figure object (can be converted to HTML or PNG)
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["rate"] * 100,  # Convert to percentage
            mode="lines+markers",
            name="Interest Rate",
            line=dict(color="#FF6B9D", width=2),
            marker=dict(size=5, color="#FF6B9D"),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Rate: %{y:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title="Interest Rate Over Time",
        xaxis_title="Date",
        yaxis_title="Rate (%)",
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

    logger.debug("Rate chart generated")
    return fig


def format_kpi_tiles_html(kpis: Dict[str, float]) -> str:
    """
    Format KPI data as HTML tiles (6 tiles: 2x3 or responsive).

    Args:
        kpis: Dict from compute_kpis()

    Returns:
        HTML string for KPI tiles
    """
    tiles = [
        {
            "label": "Start Balance",
            "value": f"${kpis['start_balance']:,.0f}",
            "icon": "📊",
        },
        {
            "label": "End Balance",
            "value": f"${kpis['end_balance']:,.0f}",
            "icon": "💰",
        },
        {
            "label": "% Change",
            "value": f"{kpis['pct_change']:+.2f}%",
            "icon": "📈" if kpis["pct_change"] >= 0 else "📉",
        },
        {
            "label": "Avg Rate",
            "value": f"{kpis['avg_rate']*100:.2f}%",
            "icon": "📋",
        },
        {
            "label": "Rate Change",
            "value": f"{kpis['rate_change_bps']:+.0f} bps",
            "icon": "⚡",
        },
        {
            "label": "Balance Volatility",
            "value": f"${kpis['balance_stdev']:,.0f}",
            "icon": "📉",
        },
    ]

    html_parts = ['<div class="kpi-grid">']
    for tile in tiles:
        html_parts.append(
            f"""
        <div class="kpi-tile">
            <div class="kpi-icon">{tile['icon']}</div>
            <div class="kpi-label">{tile['label']}</div>
            <div class="kpi-value">{tile['value']}</div>
        </div>
        """
        )
    html_parts.append("</div>")

    logger.debug("KPI tiles formatted")
    return "".join(html_parts)


def generate_kpi_narrative(kpis: Dict[str, float], flags: Dict[str, Any]) -> str:
    """
    Generate plain-language narrative summary from KPIs and flags.

    Args:
        kpis: Dict from compute_kpis()
        flags: Dict from detect_flags()

    Returns:
        HTML string with 1-2 paragraphs
    """
    parts = []

    # Paragraph 1: Main trend
    direction = "increased" if kpis["pct_change"] >= 0 else "decreased"
    parts.append(
        f"<p><strong>Balance Trend:</strong> The loan balance {direction} by "
        f"{abs(kpis['pct_change']):.2f}% over the observation period, from "
        f"${kpis['start_balance']:,.0f} to ${kpis['end_balance']:,.0f}. "
        f"The average interest rate was {kpis['avg_rate']*100:.2f}%, "
        f"with a movement of {kpis['rate_change_bps']:+.0f} basis points.</p>"
    )

    # Paragraph 2: Risk indicators
    risk_items = []
    if flags["volatility_spike"]:
        risk_items.append(
            f"significant balance volatility (${kpis['balance_stdev']:,.0f} std dev)"
        )
    if flags["trend_change"]:
        risk_items.append("changes in the direction of balance movements")
    if flags["missing_dates"]:
        risk_items.append("gaps in reporting dates")
    if flags["outlier_count"] > 0:
        risk_items.append(f"{flags['outlier_count']} statistical outliers")

    if risk_items:
        risk_str = ", ".join(risk_items)
        parts.append(
            f"<p><strong>Risk Indicators:</strong> Analysis detected {risk_str}. "
            f"Review data quality and business drivers for these anomalies.</p>"
        )
    else:
        parts.append(
            "<p><strong>Risk Indicators:</strong> No major anomalies detected. "
            "The loan shows consistent patterns.</p>"
        )

    html = "".join(parts)
    logger.debug("Narrative generated")
    return html
