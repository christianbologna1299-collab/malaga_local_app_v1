"""
Sheet 9: Strategy & Industry Analysis — Porter's Five Forces + SWOT placeholder.
"""

from features.equity.excel.styles import (
    apply_title_row, apply_freeze_panes, set_column_widths,
    BODY_FONT, SUBTOTAL_FONT, HIGHLIGHT_FONT,
    INPUT_FILL, INPUT_BORDER,
    RATIO_FORMAT,
    RIGHT_ALIGN, CENTER_ALIGN, LEFT_ALIGN,
    THIN_BORDER, BOTTOM_BORDER,
    HEADER_FILL, HEADER_FONT,
    GREEN_TINT_FILL, RED_TINT_FILL, GOLD_FILL,
)


def _porter_assessment(score):
    """Convert 1-5 score to Low/Medium/High assessment."""
    if score <= 2:
        return "Low"
    elif score == 3:
        return "Medium"
    else:
        return "High"


def build_strategy_sheet(ws, snapshot, outputs):
    """Populate strategy sheet with Porter's Five Forces and placeholders."""
    porter = snapshot["strategy"]["porter_scores"]

    set_column_widths(ws, {"A": 2, "B": 32, "C": 12, "D": 14, "E": 40})

    # Title
    ws.merge_cells("B1:E1")
    ws["B1"] = "Strategy & Industry Analysis"
    apply_title_row(ws, 1, 5)
    apply_freeze_panes(ws, "A3")

    # Porter's Five Forces
    ws.cell(row=3, column=2, value="Porter's Five Forces").font = HIGHLIGHT_FONT
    ws.cell(row=3, column=2).border = BOTTOM_BORDER

    # Column headers
    r = 4
    for j, hdr in enumerate(["Force", "Score (1-5)", "Assessment", "Notes"]):
        c = ws.cell(row=r, column=2 + j, value=hdr)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER_ALIGN

    forces = [
        ("Threat of New Entrants", porter["new_entrants"]),
        ("Bargaining Power of Suppliers", porter["suppliers"]),
        ("Bargaining Power of Buyers", porter["buyers"]),
        ("Threat of Substitutes", porter["substitutes"]),
        ("Competitive Rivalry", porter["rivalry"]),
    ]
    for i, (name, score) in enumerate(forces):
        row = 5 + i
        ws.cell(row=row, column=2, value=name).font = BODY_FONT
        sc = ws.cell(row=row, column=3, value=score)
        sc.alignment = CENTER_ALIGN
        sc.fill = INPUT_FILL
        sc.border = INPUT_BORDER
        assessment = _porter_assessment(score)
        ac = ws.cell(row=row, column=4, value=assessment)
        ac.alignment = CENTER_ALIGN
        if assessment == "Low":
            ac.fill = GREEN_TINT_FILL
        elif assessment == "High":
            ac.fill = RED_TINT_FILL
        else:
            ac.fill = GOLD_FILL
        # Notes cell (editable)
        nc = ws.cell(row=row, column=5, value="")
        nc.fill = INPUT_FILL
        nc.border = INPUT_BORDER

    # Industry Attractiveness (average)
    r = 10
    scores = [s for _, s in forces]
    avg = sum(scores) / len(scores)
    ws.cell(row=r, column=2, value="Industry Attractiveness (Avg)").font = SUBTOTAL_FONT
    c = ws.cell(row=r, column=3, value=round(avg, 1))
    c.number_format = RATIO_FORMAT
    c.alignment = CENTER_ALIGN
    c.font = SUBTOTAL_FONT
    c.border = THIN_BORDER
    assessment = _porter_assessment(round(avg))
    ws.cell(row=r, column=4, value=assessment).font = SUBTOTAL_FONT

    # SWOT Placeholder
    r = 12
    ws.cell(row=r, column=2, value="SWOT Analysis").font = HIGHLIGHT_FONT
    ws.cell(row=r, column=2).border = BOTTOM_BORDER

    swot = [
        ("Strengths", "B14:C16"),
        ("Weaknesses", "D14:E16"),
        ("Opportunities", "B18:C20"),
        ("Threats", "D18:E20"),
    ]
    positions = [
        (13, 2, "Strengths"),
        (13, 4, "Weaknesses"),
        (17, 2, "Opportunities"),
        (17, 4, "Threats"),
    ]
    for row_pos, col, label in positions:
        c = ws.cell(row=row_pos, column=col, value=label)
        c.font = SUBTOTAL_FONT
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        # Editable cell below
        ec = ws.cell(row=row_pos + 1, column=col, value="")
        ec.fill = INPUT_FILL
        ec.border = INPUT_BORDER

    # Key Risks
    r = 22
    ws.cell(row=r, column=2, value="Key Risks").font = HIGHLIGHT_FONT
    ws.cell(row=r, column=2).border = BOTTOM_BORDER
    for i in range(1, 6):
        row = 22 + i
        ws.cell(row=row, column=2, value=f"{i}.").font = BODY_FONT
        ec = ws.cell(row=row, column=3, value="")
        ec.fill = INPUT_FILL
        ec.border = INPUT_BORDER
