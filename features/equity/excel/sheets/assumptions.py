"""
Sheet 2: Assumptions — All model inputs, marked with INPUT styling.
"""

from features.equity.excel.styles import (
    apply_title_row, apply_freeze_panes, set_column_widths,
    BODY_FONT, SUBTOTAL_FONT, HIGHLIGHT_FONT,
    INPUT_FILL, INPUT_BORDER,
    PERCENT_FORMAT, CURRENCY_FORMAT, RATIO_FORMAT,
    LEFT_ALIGN, RIGHT_ALIGN,
)


def _input_cell(ws, row, col, value, fmt=None):
    """Write a value and apply INPUT styling."""
    c = ws.cell(row=row, column=col, value=value)
    c.fill = INPUT_FILL
    c.border = INPUT_BORDER
    c.font = BODY_FONT
    c.alignment = RIGHT_ALIGN
    if fmt:
        c.number_format = fmt
    return c


def build_assumptions_sheet(ws, snapshot, outputs):
    """Populate the Assumptions sheet with all driver inputs."""
    a = outputs["assumptions"]
    max_col = 3
    set_column_widths(ws, {"A": 2, "B": 35, "C": 18})

    # Header
    ws.merge_cells("B1:C1")
    ws["B1"] = "Model Assumptions"
    apply_title_row(ws, 1, max_col)
    apply_freeze_panes(ws, "A3")

    # Revenue Drivers (rows 4-8)
    ws.cell(row=3, column=2, value="Revenue Drivers").font = HIGHLIGHT_FONT
    items = [
        ("Revenue CAGR", a["revenue_cagr"], PERCENT_FORMAT),
        ("Base Revenue ($M)", snapshot["historic_financials"]["revenue"][-1], CURRENCY_FORMAT),
        ("Projection Years", a["projection_years"], "0"),
    ]
    for i, (label, value, fmt) in enumerate(items):
        r = 4 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        _input_cell(ws, r, 3, value, fmt)

    # Margin Assumptions (rows 9-13)
    ws.cell(row=8, column=2, value="Margin Assumptions").font = HIGHLIGHT_FONT
    margins = [
        ("COGS %", a["cogs_pct"], PERCENT_FORMAT),
        ("SGA %", a["sga_pct"], PERCENT_FORMAT),
        ("D&A %", a["da_pct"], PERCENT_FORMAT),
        ("Tax Rate", a["tax_rate"], PERCENT_FORMAT),
    ]
    for i, (label, value, fmt) in enumerate(margins):
        r = 9 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        _input_cell(ws, r, 3, value, fmt)

    # Capital Structure (rows 14-19)
    ws.cell(row=14, column=2, value="Capital Structure").font = HIGHLIGHT_FONT
    cap = [
        ("Risk-free Rate", a["risk_free_rate"], PERCENT_FORMAT),
        ("Equity Risk Premium", a["equity_risk_premium"], PERCENT_FORMAT),
        ("Beta", a["beta"], RATIO_FORMAT),
        ("Cost of Debt", a["cost_of_debt"], PERCENT_FORMAT),
    ]
    for i, (label, value, fmt) in enumerate(cap):
        r = 15 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        _input_cell(ws, r, 3, value, fmt)

    # Valuation Inputs (rows 20-24)
    ws.cell(row=20, column=2, value="Valuation Inputs").font = HIGHLIGHT_FONT
    val = [
        ("Terminal Growth Rate", a["terminal_growth"], PERCENT_FORMAT),
        ("Shares Outstanding ($M)", snapshot["shares_outstanding"], CURRENCY_FORMAT),
        ("Net Debt ($M)", snapshot["net_debt"], CURRENCY_FORMAT),
        ("Cash ($M)", snapshot["cash"], CURRENCY_FORMAT),
    ]
    for i, (label, value, fmt) in enumerate(val):
        r = 21 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        _input_cell(ws, r, 3, value, fmt)

    # Working Capital (rows 26-29)
    ws.cell(row=26, column=2, value="Working Capital").font = HIGHLIGHT_FONT
    wc = [
        ("DSO (days)", a["dso"], "0"),
        ("DIO (days)", a["dio"], "0"),
        ("DPO (days)", a["dpo"], "0"),
        ("CapEx % of Revenue", a["capex_pct_revenue"], PERCENT_FORMAT),
    ]
    for i, (label, value, fmt) in enumerate(wc):
        r = 27 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        _input_cell(ws, r, 3, value, fmt)
