"""
Sheet 1: Overview — Executive summary with cross-references.
"""

from features.equity.excel.styles import (
    apply_title_row, apply_freeze_panes, set_column_widths,
    BODY_FONT, SUBTOTAL_FONT, HIGHLIGHT_FONT, LINK_FONT,
    CURRENCY_FORMAT, PERCENT_FORMAT, PRICE_FORMAT,
    LEFT_ALIGN, RIGHT_ALIGN, THIN_BORDER,
)


def build_overview_sheet(ws, snapshot, outputs):
    """Populate the Overview sheet with executive summary data."""
    max_col = 3
    set_column_widths(ws, {"A": 2, "B": 30, "C": 25})

    # Row 1-2: Header
    ws.merge_cells("B1:C1")
    ws["B1"] = "Equity Research Report"
    apply_title_row(ws, 1, max_col)

    ws.merge_cells("B2:C2")
    ws["B2"] = f"Generated: {outputs.get('generated_at', 'N/A')}"
    ws["B2"].font = BODY_FONT

    apply_freeze_panes(ws, "A3")

    # Company ID block (rows 4-8)
    fields = [
        ("Ticker", snapshot["ticker"]),
        ("Company Name", snapshot["company_name"]),
        ("Sector", snapshot["sector"]),
        ("Exchange", snapshot["exchange"]),
        ("As-of Date", snapshot.get("asof_date", "N/A")),
    ]
    for i, (label, value) in enumerate(fields):
        r = 4 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        ws.cell(row=r, column=3, value=value).font = SUBTOTAL_FONT

    # Market Data block (rows 10-14)
    ws.cell(row=10, column=2, value="Market Data").font = HIGHLIGHT_FONT
    ws.cell(row=10, column=2).border = THIN_BORDER
    market_items = [
        ("Current Price", snapshot["current_price"], PRICE_FORMAT),
        ("Market Cap ($M)", snapshot["market_cap"], CURRENCY_FORMAT),
        ("Enterprise Value ($M)", snapshot["enterprise_value"], CURRENCY_FORMAT),
        ("52-Week High", snapshot["high_52w"], PRICE_FORMAT),
        ("52-Week Low", snapshot["low_52w"], PRICE_FORMAT),
    ]
    for i, (label, value, fmt) in enumerate(market_items):
        r = 11 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        c = ws.cell(row=r, column=3, value=value)
        c.font = SUBTOTAL_FONT
        c.number_format = fmt
        c.alignment = RIGHT_ALIGN

    # Valuation Summary (rows 17-22)
    dcf = outputs["dcf"]
    ws.cell(row=17, column=2, value="Valuation Summary").font = HIGHLIGHT_FONT
    ws.cell(row=17, column=2).border = THIN_BORDER
    implied = dcf["implied_price"]
    current = snapshot["current_price"]
    upside = (implied - current) / current if current else 0

    val_items = [
        ("Implied Share Price", implied, PRICE_FORMAT),
        ("Upside / Downside", upside, PERCENT_FORMAT),
        ("WACC", outputs["wacc_calc"]["wacc"], PERCENT_FORMAT),
        ("Terminal Growth Rate", dcf["terminal_growth"], PERCENT_FORMAT),
        ("Revenue CAGR (assumed)", outputs["assumptions"]["revenue_cagr"], PERCENT_FORMAT),
    ]
    for i, (label, value, fmt) in enumerate(val_items):
        r = 18 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        c = ws.cell(row=r, column=3, value=value)
        c.font = SUBTOTAL_FONT
        c.number_format = fmt
        c.alignment = RIGHT_ALIGN

    # Key Outputs (rows 24-29)
    hist = snapshot["historic_financials"]
    ws.cell(row=24, column=2, value="Key Financials (LTM)").font = HIGHLIGHT_FONT
    ws.cell(row=24, column=2).border = THIN_BORDER
    rev_ltm = hist["revenue"][-1]
    ebitda_ltm = hist["ebitda"][-1]
    ni_ltm = hist["net_income"][-1]
    ev_ebitda = snapshot["enterprise_value"] / ebitda_ltm if ebitda_ltm else 0
    pe = snapshot["market_cap"] / ni_ltm if ni_ltm else 0

    key_items = [
        ("Revenue ($M)", rev_ltm, CURRENCY_FORMAT),
        ("EBITDA ($M)", ebitda_ltm, CURRENCY_FORMAT),
        ("Net Income ($M)", ni_ltm, CURRENCY_FORMAT),
        ("EV / EBITDA", round(ev_ebitda, 1), "0.0x"),
        ("P / E", round(pe, 1), "0.0x"),
    ]
    for i, (label, value, fmt) in enumerate(key_items):
        r = 25 + i
        ws.cell(row=r, column=2, value=label).font = BODY_FONT
        c = ws.cell(row=r, column=3, value=value)
        c.font = SUBTOTAL_FONT
        c.number_format = fmt
        c.alignment = RIGHT_ALIGN

    # Navigation links (rows 31-39)
    ws.cell(row=31, column=2, value="Sheet Navigation").font = HIGHLIGHT_FONT
    ws.cell(row=31, column=2).border = THIN_BORDER
    sheets = [
        "Assumptions", "Income Statement", "Balance Sheet",
        "Cash Flow", "DCF", "Sensitivity",
        "Quant Tearsheet", "Strategy",
    ]
    for i, name in enumerate(sheets):
        r = 32 + i
        c = ws.cell(row=r, column=2, value=name)
        c.font = LINK_FONT
