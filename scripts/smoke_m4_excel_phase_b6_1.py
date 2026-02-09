#!/usr/bin/env python3
"""
M4.01 Phase B6.1 Smoke Test — Overview Print-Ready (1-Page Handout).

Verifies:
  - Overview sheet page setup: landscape, letter, fit-to-page
  - Margins match spec (0.5 LR, 0.75 TB, 0.3 HF)
  - horizontalCentered=True, verticalCentered=False
  - Print titles set to "1:1"
  - Print area computed dynamically, starts with "A1:", col <= L, row <= 80
  - Header: left="Banker Analytics", center="Loan Scenario Report", right="Exported:..."
  - Footer: left="Session:...", right="Page &P of &N"
  - Save/reload persistence of all settings
  - Helper functions exist and work correctly

Usage: python scripts/smoke_m4_excel_phase_b6_1.py
Exit code 0 = PASS, nonzero = FAIL
"""

import sys
import os
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASSED = 0
FAILED = 0


def check(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name} — {detail}")


def approx(a, b, tol=0.01):
    """Float comparison within tolerance."""
    return abs(float(a) - float(b)) < tol


def main():
    global PASSED, FAILED

    from features.excel_export import (
        _build_skeleton_workbook,
        LoanInputs, ScenarioConfig, SeriesData, ExportMeta, ExportLayout,
        _col_letter, _format_export_ts, _infer_print_area,
        _apply_overview_print_setup,
    )
    from openpyxl import load_workbook

    print("=" * 60)
    print("M4.01 PHASE B6.1 SMOKE TEST — Overview Print-Ready")
    print("=" * 60)

    # ---- Generate workbook ----
    loan = LoanInputs(
        principal=500_000, start_date="2024-01-15",
        term_months=360, rate=6.25,
        payment_frequency="Monthly",
    )
    scenario = ScenarioConfig(rate_shock_bps=100, balance_shock_pct=5.0, stress_toggle=True)
    series = SeriesData(
        dates=["2024-01-15", "2024-02-15", "2024-03-15"],
        balances=[500000, 499500, 499000],
        rates=[0.0625, 0.0625, 0.0625],
    )
    meta = ExportMeta(session_id="b61-test-session-001", data_points=3)
    wb = _build_skeleton_workbook(loan, scenario, series, meta)

    # ---- Section 1: Helper functions exist ----
    print("\n--- Helper Functions ---")
    check("_col_letter exists", callable(_col_letter))
    check("_col_letter(1) == 'A'", _col_letter(1) == "A", f"got {_col_letter(1)}")
    check("_col_letter(2) == 'B'", _col_letter(2) == "B", f"got {_col_letter(2)}")
    check("_col_letter(12) == 'L'", _col_letter(12) == "L", f"got {_col_letter(12)}")

    check("_format_export_ts exists", callable(_format_export_ts))
    test_dt = datetime(2024, 6, 15, 14, 30, 0)
    ts_out = _format_export_ts(test_dt)
    check("_format_export_ts format", ts_out == "Exported: 2024-06-15 14:30", f"got {ts_out}")

    check("_infer_print_area exists", callable(_infer_print_area))
    check("_apply_overview_print_setup exists", callable(_apply_overview_print_setup))
    check("ExportLayout exists", ExportLayout is not None)

    # ---- Section 2: Overview sheet page setup ----
    print("\n--- Overview Page Setup ---")
    ws = wb["Overview"]

    check("orientation is landscape",
          ws.page_setup.orientation == "landscape",
          f"got {ws.page_setup.orientation}")
    check("paperSize is letter (1)",
          str(ws.page_setup.paperSize) == "1",
          f"got {ws.page_setup.paperSize}")
    check("fitToWidth == 1",
          ws.page_setup.fitToWidth == 1,
          f"got {ws.page_setup.fitToWidth}")
    check("fitToHeight == 1",
          ws.page_setup.fitToHeight == 1,
          f"got {ws.page_setup.fitToHeight}")

    # ---- Section 3: Centering ----
    print("\n--- Print Centering ---")
    check("horizontalCentered == True",
          ws.print_options.horizontalCentered is True,
          f"got {ws.print_options.horizontalCentered}")
    check("verticalCentered == False",
          not ws.print_options.verticalCentered,
          f"got {ws.print_options.verticalCentered}")

    # ---- Section 4: Margins ----
    print("\n--- Margins ---")
    check("left margin == 0.5", approx(ws.page_margins.left, 0.5),
          f"got {ws.page_margins.left}")
    check("right margin == 0.5", approx(ws.page_margins.right, 0.5),
          f"got {ws.page_margins.right}")
    check("top margin == 0.75", approx(ws.page_margins.top, 0.75),
          f"got {ws.page_margins.top}")
    check("bottom margin == 0.75", approx(ws.page_margins.bottom, 0.75),
          f"got {ws.page_margins.bottom}")
    check("header margin == 0.3", approx(ws.page_margins.header, 0.3),
          f"got {ws.page_margins.header}")
    check("footer margin == 0.3", approx(ws.page_margins.footer, 0.3),
          f"got {ws.page_margins.footer}")

    # ---- Section 5: Print titles ----
    print("\n--- Print Titles ---")
    pt = ws.print_title_rows
    check("print_title_rows set", pt is not None, "not set")
    # openpyxl stores as "$1:$1"
    check("print_title_rows contains row 1",
          pt is not None and ("1:1" in str(pt) or "$1:$1" in str(pt)),
          f"got {pt}")

    # ---- Section 6: Print area ----
    print("\n--- Print Area ---")
    pa = ws.print_area
    # openpyxl may return a string or list
    pa_str = str(pa) if pa else ""
    check("print_area exists", bool(pa_str), "not set")
    # openpyxl may include sheet name: "'Overview'!$A$1:$B$21"
    check("print_area starts with A1:",
          "A1:" in pa_str or "$A$1:" in pa_str,
          f"got {pa_str}")

    # Extract last col letter from print area
    # Formats could be "A1:B21", "$A$1:$B$21", or "'Overview'!$A$1:$B$21"
    clean_pa = pa_str.replace("$", "")
    if "!" in clean_pa:
        clean_pa = clean_pa.split("!")[1]
    if ":" in clean_pa:
        end_ref = clean_pa.split(":")[1]
        last_col_letter = "".join(c for c in end_ref if c.isalpha())
        last_row_num = "".join(c for c in end_ref if c.isdigit())
        check("last col <= L", last_col_letter <= "L",
              f"got {last_col_letter}")
        check("last row <= 80",
              int(last_row_num) <= 80 if last_row_num.isdigit() else False,
              f"got {last_row_num}")

    # ---- Section 7: Inferred print area test ----
    print("\n--- _infer_print_area ---")
    min_r, min_c, max_r, max_c = _infer_print_area(ws)
    check("infer min_row == 1", min_r == 1, f"got {min_r}")
    check("infer min_col == 1", min_c == 1, f"got {min_c}")
    check("infer max_col <= 12", max_c <= 12, f"got {max_c}")
    check("infer max_row <= 80", max_r <= 80, f"got {max_r}")
    check("infer max_row >= 18", max_r >= 18, f"got {max_r} (too small)")

    # ---- Section 8: Header / Footer ----
    print("\n--- Header / Footer ---")
    hdr_left = ws.oddHeader.left.text if ws.oddHeader.left else ""
    hdr_center = ws.oddHeader.center.text if ws.oddHeader.center else ""
    hdr_right = ws.oddHeader.right.text if ws.oddHeader.right else ""
    ftr_left = ws.oddFooter.left.text if ws.oddFooter.left else ""
    ftr_right = ws.oddFooter.right.text if ws.oddFooter.right else ""

    check("header left contains 'Banker Analytics'",
          "Banker Analytics" in (hdr_left or ""),
          f"got '{hdr_left}'")
    check("header center contains 'Loan Scenario Report'",
          "Loan Scenario Report" in (hdr_center or ""),
          f"got '{hdr_center}'")
    check("header right contains 'Exported:'",
          "Exported:" in (hdr_right or ""),
          f"got '{hdr_right}'")
    check("footer left contains 'Session:'",
          "Session:" in (ftr_left or ""),
          f"got '{ftr_left}'")
    check("footer right contains 'Page'",
          "Page" in (ftr_right or ""),
          f"got '{ftr_right}'")
    check("footer right contains '&P'",
          "&P" in (ftr_right or ""),
          f"got '{ftr_right}'")

    # ---- Section 9: Save/Reload Persistence ----
    print("\n--- Save/Reload Persistence ---")
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_path = f.name
    try:
        wb.save(tmp_path)
        wb2 = load_workbook(tmp_path)
        ws2 = wb2["Overview"]

        check("reload: orientation is landscape",
              ws2.page_setup.orientation == "landscape",
              f"got {ws2.page_setup.orientation}")
        check("reload: paperSize is letter",
              str(ws2.page_setup.paperSize) == "1",
              f"got {ws2.page_setup.paperSize}")
        check("reload: fitToWidth == 1",
              ws2.page_setup.fitToWidth == 1,
              f"got {ws2.page_setup.fitToWidth}")
        check("reload: fitToHeight == 1",
              ws2.page_setup.fitToHeight == 1,
              f"got {ws2.page_setup.fitToHeight}")

        check("reload: horizontalCentered",
              ws2.print_options.horizontalCentered is True,
              f"got {ws2.print_options.horizontalCentered}")

        check("reload: left margin",
              approx(ws2.page_margins.left, 0.5),
              f"got {ws2.page_margins.left}")
        check("reload: top margin",
              approx(ws2.page_margins.top, 0.75),
              f"got {ws2.page_margins.top}")
        check("reload: header margin",
              approx(ws2.page_margins.header, 0.3),
              f"got {ws2.page_margins.header}")

        # Print area
        pa2 = ws2.print_area
        pa2_str = str(pa2) if pa2 else ""
        check("reload: print_area exists", bool(pa2_str), "not set")
        check("reload: print_area starts with A1",
              "A1" in pa2_str or "$A$1" in pa2_str,
              f"got {pa2_str}")

        # Print titles
        pt2 = ws2.print_title_rows
        check("reload: print_title_rows set", pt2 is not None, "not set")
        check("reload: print_title_rows contains row 1",
              pt2 is not None and ("1:1" in str(pt2) or "$1:$1" in str(pt2)),
              f"got {pt2}")

        # Header/footer
        h2_left = ws2.oddHeader.left.text if ws2.oddHeader.left else ""
        h2_center = ws2.oddHeader.center.text if ws2.oddHeader.center else ""
        h2_right = ws2.oddHeader.right.text if ws2.oddHeader.right else ""
        f2_left = ws2.oddFooter.left.text if ws2.oddFooter.left else ""
        f2_right = ws2.oddFooter.right.text if ws2.oddFooter.right else ""

        check("reload: header left 'Banker Analytics'",
              "Banker Analytics" in (h2_left or ""),
              f"got '{h2_left}'")
        check("reload: header center 'Loan Scenario Report'",
              "Loan Scenario Report" in (h2_center or ""),
              f"got '{h2_center}'")
        check("reload: header right 'Exported:'",
              "Exported:" in (h2_right or ""),
              f"got '{h2_right}'")
        check("reload: footer left 'Session:'",
              "Session:" in (f2_left or ""),
              f"got '{f2_left}'")
        check("reload: footer right 'Page'",
              "Page" in (f2_right or ""),
              f"got '{f2_right}'")

        # ---- Section 10: Other sheets unaffected ----
        print("\n--- Other Sheets Unaffected ---")
        ws_sc = wb2["Scenarios"]
        sc_hdr = ws_sc.oddHeader.center.text if ws_sc.oddHeader.center else ""
        check("Scenarios header unchanged (Confidential)",
              "Confidential" in (sc_hdr or ""),
              f"got '{sc_hdr}'")

        # Named ranges intact
        nr_names = list(wb2.defined_names.values())
        check("reload: 15 named ranges",
              len(nr_names) >= 15,
              f"got {len(nr_names)}")

        # Protection intact
        check("reload: Overview still protected",
              ws2.protection.sheet is True,
              f"got {ws2.protection.sheet}")

        wb2.close()
    finally:
        os.unlink(tmp_path)

    # ---- Summary ----
    print()
    print("=" * 60)
    print(f"Results: {PASSED}/{PASSED + FAILED} passed, {FAILED} failed")
    if FAILED == 0:
        print("M4.01 PHASE B6.1 SMOKE TESTS: ALL PASSED")
    else:
        print("M4.01 PHASE B6.1 SMOKE TESTS: FAILURES DETECTED")
    print("=" * 60)
    return FAILED


if __name__ == "__main__":
    sys.exit(main())
