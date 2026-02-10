"""
Sheet 7: Sensitivity Analysis — 5x5 WACC x Terminal Growth grid + Scenario table.
"""

from features.equity.excel.styles import (
    apply_title_row, apply_freeze_panes, set_column_widths,
    BODY_FONT, SUBTOTAL_FONT, HIGHLIGHT_FONT,
    GOLD_FILL, GREEN_TINT_FILL, RED_TINT_FILL,
    PERCENT_FORMAT, PRICE_FORMAT,
    RIGHT_ALIGN, CENTER_ALIGN, THIN_BORDER, BOTTOM_BORDER,
    HEADER_FILL, HEADER_FONT,
)


def build_sensitivity_sheet(ws, snapshot, outputs):
    """Populate sensitivity analysis grid and scenario table."""
    grid = outputs["sensitivity_grid"]
    dcf = outputs["dcf"]
    base_price = dcf["implied_price"]

    set_column_widths(ws, {"A": 2, "B": 20, "C": 14, "D": 14, "E": 14, "F": 14, "G": 14})

    # Title
    ws.merge_cells("B1:G1")
    ws["B1"] = "Sensitivity Analysis"
    apply_title_row(ws, 1, 7)

    # Grid title
    ws.cell(row=3, column=2, value="WACC x Terminal Growth Rate - Implied Share Price").font = HIGHLIGHT_FONT

    # Column headers (growth rates)
    ws.cell(row=5, column=2, value="WACC \\ Growth").font = SUBTOTAL_FONT
    ws.cell(row=5, column=2).fill = HEADER_FILL
    ws.cell(row=5, column=2).font = HEADER_FONT
    for j, g in enumerate(grid["growth_values"]):
        c = ws.cell(row=5, column=3 + j, value=g)
        c.number_format = PERCENT_FORMAT
        c.alignment = CENTER_ALIGN
        c.font = HEADER_FONT
        c.fill = HEADER_FILL

    # Grid rows
    for i, w in enumerate(grid["wacc_values"]):
        row = 6 + i
        c = ws.cell(row=row, column=2, value=w)
        c.number_format = PERCENT_FORMAT
        c.font = SUBTOTAL_FONT
        c.alignment = RIGHT_ALIGN

        for j, price in enumerate(grid["prices"][i]):
            cell = ws.cell(row=row, column=3 + j, value=price)
            cell.number_format = PRICE_FORMAT
            cell.alignment = RIGHT_ALIGN

            # Color gradient
            if i == 2 and j == 2:
                # Center cell = base case
                cell.fill = GOLD_FILL
                cell.font = HIGHLIGHT_FONT
                cell.border = THIN_BORDER
            elif price > base_price:
                cell.fill = GREEN_TINT_FILL
            elif price < base_price and price > 0:
                cell.fill = RED_TINT_FILL

    # Scenario table (rows 13-18)
    r = 13
    ws.cell(row=r, column=2, value="Scenario Analysis").font = HIGHLIGHT_FONT
    ws.cell(row=r, column=2).border = BOTTOM_BORDER

    # Headers
    r = 14
    for j, hdr in enumerate(["Scenario", "Rev Growth", "EBITDA Margin", "Implied Price"]):
        c = ws.cell(row=r, column=2 + j, value=hdr)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER_ALIGN

    # Scenarios derived from sensitivity grid
    a = outputs["assumptions"]
    scenarios = [
        ("Bull Case", a["revenue_cagr"] + 0.05, 0.35, grid["prices"][0][4] if grid["prices"][0][4] else base_price * 1.2, GREEN_TINT_FILL),
        ("Base Case", a["revenue_cagr"], 0.30, base_price, None),
        ("Bear Case", a["revenue_cagr"] - 0.05, 0.25, grid["prices"][4][0] if grid["prices"][4][0] else base_price * 0.8, RED_TINT_FILL),
    ]
    for i, (name, rev_g, margin, price, fill) in enumerate(scenarios):
        row = 15 + i
        ws.cell(row=row, column=2, value=name).font = SUBTOTAL_FONT
        ws.cell(row=row, column=3, value=rev_g).number_format = PERCENT_FORMAT
        ws.cell(row=row, column=4, value=margin).number_format = PERCENT_FORMAT
        c = ws.cell(row=row, column=5, value=price)
        c.number_format = PRICE_FORMAT
        c.alignment = RIGHT_ALIGN
        if fill:
            for col in range(2, 6):
                ws.cell(row=row, column=col).fill = fill
