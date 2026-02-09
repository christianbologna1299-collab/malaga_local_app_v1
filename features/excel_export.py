"""
M4.01 Phase B1: Excel Export Engine — Formula-Driven Amortization.

Produces a banker-grade interactive .xlsx workbook with:
  - Overview, Loan Inputs, Amortization, Scenarios, Charts sheets
  - Named ranges, data validation dropdowns, freeze panes
  - Dark header strip (printable body), currency/percent formatting
  - Formula-driven amortization: inputs change → schedule recalculates
  - Derived values (Periods/Year, Periodic Rate, Total Periods, Payment)
  - 360-row IF-guarded formula grid with zebra striping

Entry point: build_excel_workbook(...)
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Literal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from starlette.requests import Request

logger = logging.getLogger(__name__)

# Lazy imports for app-level helpers (avoid circular at module level)
_app_helpers_loaded = False
_safe_json_dumps = None
_get_client_ip = None
_policy_log_event = None
_policy_guard = None
_db = None


def _ensure_app_helpers():
    """Lazy-load app-level helpers to avoid circular imports."""
    global _app_helpers_loaded, _safe_json_dumps, _get_client_ip
    global _policy_log_event, _policy_guard, _db
    if _app_helpers_loaded:
        return
    try:
        from app import safe_json_dumps, get_client_ip, db
        from core.policy import policy_log_event, policy_guard
        _safe_json_dumps = safe_json_dumps
        _get_client_ip = get_client_ip
        _policy_log_event = policy_log_event
        _policy_guard = policy_guard
        _db = db
    except ImportError:
        # Fallback for smoke tests or standalone usage
        import json

        def _safe_json_dumps(obj):
            try:
                return json.dumps(obj, default=str)
            except Exception:
                return '{"error":"serialization_failed"}'

        def _get_client_ip(request):
            return None

        def _policy_log_event(**kwargs):
            pass

        def _policy_guard(ctx):
            pass

        _db = None
    _app_helpers_loaded = True


# =============================================================================
# Dataclasses for typed payloads
# =============================================================================

@dataclass
class LoanInputs:
    principal: float
    start_date: str  # ISO YYYY-MM-DD
    term_months: int
    rate: float  # APR percent (e.g. 6.25)
    payment_frequency: str  # "Monthly" initially
    fees: float | None = None
    amort_type: str = "Level Payment"
    interest_only_months: int | None = None


@dataclass
class ScenarioConfig:
    rate_shock_bps: int
    balance_shock_pct: float
    stress_toggle: bool


@dataclass
class SeriesData:
    dates: list[str]  # ISO strings
    balances: list[float]
    rates: list[float]


# =============================================================================
# Formatting constants
# =============================================================================

_HEADER_FILL = PatternFill(start_color="1B2A4A", end_color="1B2A4A", fill_type="solid")
_HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
_LABEL_FONT = Font(name="Calibri", bold=True, size=10)
_BODY_FONT = Font(name="Calibri", size=10)
_THIN_BORDER = Border(
    left=Side(style="thin", color="D0D0D0"),
    right=Side(style="thin", color="D0D0D0"),
    top=Side(style="thin", color="D0D0D0"),
    bottom=Side(style="thin", color="D0D0D0"),
)
_CURRENCY_FMT = '#,##0.00'
_PERCENT_FMT = '0.00%'
_BPS_FMT = '#,##0'

# B1: formula-driven amortization additions
_ZEBRA_FILL = PatternFill(start_color="F2F6FA", end_color="F2F6FA", fill_type="solid")
_DATE_FMT = 'YYYY-MM-DD'
_RATE_PRECISE_FMT = '0.000000%'
_MAX_AMORT_ROWS = 360


# =============================================================================
# Skeleton workbook builder
# =============================================================================

def _apply_header_row(ws, columns: list[str], row: int = 1):
    """Apply dark header strip to row with column names."""
    for col_idx, col_name in enumerate(columns, start=1):
        cell = ws.cell(row=row, column=col_idx, value=col_name)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _THIN_BORDER


def _build_skeleton_workbook(
    loan: LoanInputs,
    scenario: ScenarioConfig,
    series: SeriesData,
) -> Workbook:
    """
    Build a banker-grade interactive workbook with 5 sheets,
    named ranges, data validation, formula-driven amortization,
    and professional formatting.

    B1 upgrade: Amortization sheet uses Excel formulas (not static data).
    Changing any input on Loan Inputs recalculates the entire schedule.

    Args:
        loan: Loan input parameters
        scenario: Scenario configuration
        series: Time series data (used for Overview data-point count)

    Returns:
        openpyxl.Workbook ready to save
    """
    wb = Workbook()

    # ------------------------------------------------------------------
    # Remove default sheet, create named sheets in order
    # ------------------------------------------------------------------
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    ws_overview = wb.create_sheet("Overview", 0)
    ws_inputs = wb.create_sheet("Loan Inputs", 1)
    ws_amort = wb.create_sheet("Amortization", 2)
    ws_scenarios = wb.create_sheet("Scenarios", 3)
    ws_charts = wb.create_sheet("Charts", 4)

    # ==================================================================
    # 1. Overview sheet
    # ==================================================================
    _apply_header_row(ws_overview, ["Banker Analytics — Excel Export"], row=1)
    ws_overview.merge_cells("A1:D1")
    ws_overview.cell(row=1, column=1).alignment = Alignment(horizontal="center")
    ws_overview["A3"] = "Report Generated"
    ws_overview["B3"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws_overview["A4"] = "Principal"
    ws_overview["B4"] = loan.principal
    ws_overview["B4"].number_format = _CURRENCY_FMT
    ws_overview["A5"] = "Rate (APR)"
    ws_overview["B5"] = loan.rate / 100
    ws_overview["B5"].number_format = _PERCENT_FMT
    ws_overview["A6"] = "Term (Months)"
    ws_overview["B6"] = loan.term_months
    ws_overview["A7"] = "Data Points"
    ws_overview["B7"] = len(series.dates)
    for row in range(3, 8):
        ws_overview.cell(row=row, column=1).font = _LABEL_FONT
        ws_overview.cell(row=row, column=2).font = _BODY_FONT
        ws_overview.cell(row=row, column=1).border = _THIN_BORDER
        ws_overview.cell(row=row, column=2).border = _THIN_BORDER
    ws_overview.column_dimensions["A"].width = 22
    ws_overview.column_dimensions["B"].width = 22

    # ==================================================================
    # 2. Loan Inputs sheet
    # ==================================================================
    _apply_header_row(ws_inputs, ["Loan Inputs", "Value", "Notes"], row=1)

    # Subheader row
    ws_inputs.cell(row=2, column=1, value="Parameter").font = _LABEL_FONT
    ws_inputs.cell(row=2, column=2, value="Current").font = _LABEL_FONT
    ws_inputs.cell(row=2, column=3, value="Description").font = _LABEL_FONT
    for c in range(1, 4):
        ws_inputs.cell(row=2, column=c).border = _THIN_BORDER

    # Parse start date to a real date for Excel compatibility (EDATE etc.)
    try:
        start_dt = datetime.strptime(loan.start_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        start_dt = date(2023, 1, 1)

    # Input data rows (rows 3–10)
    input_rows = [
        ("Amortization Type", loan.amort_type, "Amortization method"),
        ("Principal ($)", loan.principal, "Original loan amount"),
        ("Interest Rate (APR)", loan.rate / 100, "Annual percentage rate"),
        ("Term (Months)", loan.term_months, "Loan duration"),
        ("Start Date", start_dt, "Origination date"),
        ("Payment Frequency", loan.payment_frequency, "Payment schedule"),
        ("Fees ($)", loan.fees if loan.fees is not None else 0, "Origination fees"),
        ("Interest-Only Months", loan.interest_only_months or 0, "IO period length"),
    ]
    for r_idx, (label, value, note) in enumerate(input_rows, start=3):
        ws_inputs.cell(row=r_idx, column=1, value=label).font = _LABEL_FONT
        cell_val = ws_inputs.cell(row=r_idx, column=2, value=value)
        cell_val.font = _BODY_FONT
        ws_inputs.cell(row=r_idx, column=3, value=note).font = _BODY_FONT
        for c in range(1, 4):
            ws_inputs.cell(row=r_idx, column=c).border = _THIN_BORDER

    # Number formats for input cells
    ws_inputs["B4"].number_format = _CURRENCY_FMT   # Principal
    ws_inputs["B5"].number_format = _PERCENT_FMT     # Rate
    ws_inputs["B7"].number_format = _DATE_FMT        # Start Date
    ws_inputs["B9"].number_format = _CURRENCY_FMT    # Fees

    # ---- B1: Derived Values section (rows 12–16) ----
    ws_inputs.cell(row=12, column=1, value="Derived Values").font = _LABEL_FONT
    ws_inputs.cell(row=12, column=2, value="Calculated").font = _LABEL_FONT
    ws_inputs.cell(row=12, column=3, value="Description").font = _LABEL_FONT
    for c in range(1, 4):
        ws_inputs.cell(row=12, column=c).border = _THIN_BORDER

    derived_rows = [
        # (row, label, formula, fmt, note)
        (13, "Periods / Year",
         '=IF(Loan_Frequency="Monthly",12,IF(Loan_Frequency="Quarterly",4,12))',
         _BPS_FMT, "From frequency selection"),
        (14, "Periodic Rate",
         '=Loan_Rate/Periods_Per_Year',
         _RATE_PRECISE_FMT, "Per-period interest rate"),
        (15, "Total Periods",
         '=Loan_Term_Months/(12/Periods_Per_Year)',
         _BPS_FMT, "Adjusted for frequency"),
        (16, "Payment",
         '=-PMT(Periodic_Rate,Num_Periods,Loan_Principal)',
         _CURRENCY_FMT, "Level payment amount"),
    ]
    for r_idx, label, formula, fmt, note in derived_rows:
        ws_inputs.cell(row=r_idx, column=1, value=label).font = _LABEL_FONT
        cell_f = ws_inputs.cell(row=r_idx, column=2, value=formula)
        cell_f.font = _BODY_FONT
        cell_f.number_format = fmt
        ws_inputs.cell(row=r_idx, column=3, value=note).font = _BODY_FONT
        for c in range(1, 4):
            ws_inputs.cell(row=r_idx, column=c).border = _THIN_BORDER

    # Column widths
    ws_inputs.column_dimensions["A"].width = 28
    ws_inputs.column_dimensions["B"].width = 18
    ws_inputs.column_dimensions["C"].width = 22

    # Freeze panes (keep header + labels visible)
    ws_inputs.freeze_panes = "A3"

    # Data validation: Payment Frequency dropdown
    dv_freq = DataValidation(
        type="list",
        formula1='"Monthly,Quarterly,Semiannual,Annual"',
        allow_blank=False,
    )
    dv_freq.prompt = "Select payment frequency"
    dv_freq.promptTitle = "Frequency"
    ws_inputs.add_data_validation(dv_freq)
    dv_freq.add("B8")

    # Named ranges — Phase A originals
    named_ranges = {
        "Loan_Principal": "'Loan Inputs'!$B$4",
        "Loan_Rate": "'Loan Inputs'!$B$5",
        "Loan_Term_Months": "'Loan Inputs'!$B$6",
        "Loan_Start_Date": "'Loan Inputs'!$B$7",
        "Loan_Frequency": "'Loan Inputs'!$B$8",
    }
    for name, ref in named_ranges.items():
        dn = DefinedName(name, attr_text=ref)
        wb.defined_names.add(dn)

    # Named ranges — B1 derived values
    derived_names = {
        "Periods_Per_Year": "'Loan Inputs'!$B$13",
        "Periodic_Rate": "'Loan Inputs'!$B$14",
        "Num_Periods": "'Loan Inputs'!$B$15",
        "Payment": "'Loan Inputs'!$B$16",
    }
    for name, ref in derived_names.items():
        dn = DefinedName(name, attr_text=ref)
        wb.defined_names.add(dn)

    # ==================================================================
    # 3. Amortization sheet — formula-driven (B1)
    # ==================================================================
    _apply_header_row(ws_amort, ["Amortization Schedule"], row=1)
    ws_amort.merge_cells("A1:F1")
    ws_amort.cell(row=1, column=1).alignment = Alignment(horizontal="center")

    # Column headers (row 2) — 6 columns: Period, Date, Payment, Interest, Principal, Balance
    amort_cols = ["Period", "Date", "Payment", "Interest", "Principal", "Balance"]
    for col_idx, col_name in enumerate(amort_cols, start=1):
        cell = ws_amort.cell(row=2, column=col_idx, value=col_name)
        cell.font = _LABEL_FONT
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(horizontal="center")

    # Column widths
    for col_idx, width in enumerate([10, 14, 16, 16, 16, 16], start=1):
        ws_amort.column_dimensions[get_column_letter(col_idx)].width = width

    # Freeze panes
    ws_amort.freeze_panes = "A3"

    # ---- Row 3: Period 1 (special formulas — references Loan_Principal) ----
    ws_amort["A3"] = '=IF(ROW()-2>Num_Periods,"",ROW()-2)'
    ws_amort["B3"] = '=IF(A3="","",Loan_Start_Date)'
    ws_amort["C3"] = '=IF(A3="","",Payment)'
    ws_amort["D3"] = '=IF(A3="","",Loan_Principal*Periodic_Rate)'
    ws_amort["E3"] = '=IF(A3="","",C3-D3)'
    ws_amort["F3"] = '=IF(A3="","",Loan_Principal-E3)'

    # Format row 3
    for c in range(1, 7):
        cell = ws_amort.cell(row=3, column=c)
        cell.font = _BODY_FONT
        cell.border = _THIN_BORDER
    ws_amort["A3"].number_format = _BPS_FMT
    ws_amort["B3"].number_format = _DATE_FMT
    ws_amort["C3"].number_format = _CURRENCY_FMT
    ws_amort["D3"].number_format = _CURRENCY_FMT
    ws_amort["E3"].number_format = _CURRENCY_FMT
    ws_amort["F3"].number_format = _CURRENCY_FMT

    # ---- Rows 4..362: Periods 2..360 (general formulas) ----
    for r in range(4, 3 + _MAX_AMORT_ROWS):
        prev = r - 1
        ws_amort.cell(row=r, column=1, value=f'=IF(ROW()-2>Num_Periods,"",ROW()-2)')
        ws_amort.cell(row=r, column=2, value=f'=IF(A{r}="","",EDATE(B{prev},12/Periods_Per_Year))')
        ws_amort.cell(row=r, column=3, value=f'=IF(A{r}="","",Payment)')
        ws_amort.cell(row=r, column=4, value=f'=IF(A{r}="","",F{prev}*Periodic_Rate)')
        ws_amort.cell(row=r, column=5, value=f'=IF(A{r}="","",C{r}-D{r})')
        ws_amort.cell(row=r, column=6, value=f'=IF(A{r}="","",F{prev}-E{r})')

        # Formatting + zebra striping (even periods get light fill)
        is_zebra = (r - 2) % 2 == 0  # periods 2, 4, 6 ...
        for c in range(1, 7):
            cell = ws_amort.cell(row=r, column=c)
            cell.font = _BODY_FONT
            cell.border = _THIN_BORDER
            if is_zebra:
                cell.fill = _ZEBRA_FILL
        ws_amort.cell(row=r, column=1).number_format = _BPS_FMT
        ws_amort.cell(row=r, column=2).number_format = _DATE_FMT
        ws_amort.cell(row=r, column=3).number_format = _CURRENCY_FMT
        ws_amort.cell(row=r, column=4).number_format = _CURRENCY_FMT
        ws_amort.cell(row=r, column=5).number_format = _CURRENCY_FMT
        ws_amort.cell(row=r, column=6).number_format = _CURRENCY_FMT

    # Named range: Amort_Data (full data area for chart references)
    dn_amort = DefinedName("Amort_Data", attr_text="'Amortization'!$A$2:$F$362")
    wb.defined_names.add(dn_amort)

    # ==================================================================
    # 4. Scenarios sheet
    # ==================================================================
    _apply_header_row(ws_scenarios, ["Scenario Configuration", "Value", "Notes"], row=1)

    ws_scenarios.cell(row=2, column=1, value="Parameter").font = _LABEL_FONT
    ws_scenarios.cell(row=2, column=2, value="Setting").font = _LABEL_FONT
    ws_scenarios.cell(row=2, column=3, value="Description").font = _LABEL_FONT
    for c in range(1, 4):
        ws_scenarios.cell(row=2, column=c).border = _THIN_BORDER

    scenario_rows = [
        ("Scenario Name", "Base Case", "Current scenario"),
        ("Rate Shock (bps)", scenario.rate_shock_bps, "Basis point shock to rates"),
        ("Balance Shock (%)", scenario.balance_shock_pct, "Percentage shock to balance"),
        ("Stress Toggle", str(scenario.stress_toggle).upper(), "Enable stress mode"),
    ]
    for r_idx, (label, value, note) in enumerate(scenario_rows, start=3):
        ws_scenarios.cell(row=r_idx, column=1, value=label).font = _LABEL_FONT
        ws_scenarios.cell(row=r_idx, column=2, value=value).font = _BODY_FONT
        ws_scenarios.cell(row=r_idx, column=3, value=note).font = _BODY_FONT
        for c in range(1, 4):
            ws_scenarios.cell(row=r_idx, column=c).border = _THIN_BORDER

    ws_scenarios["B4"].number_format = _BPS_FMT  # Rate Shock

    ws_scenarios.column_dimensions["A"].width = 22
    ws_scenarios.column_dimensions["B"].width = 16
    ws_scenarios.column_dimensions["C"].width = 28

    # Dropdown validations
    dv_rate_shock = DataValidation(
        type="list", formula1='"-100,0,100"', allow_blank=False,
    )
    ws_scenarios.add_data_validation(dv_rate_shock)
    dv_rate_shock.add("B4")

    dv_bal_shock = DataValidation(
        type="list", formula1='"-5,0,5"', allow_blank=False,
    )
    ws_scenarios.add_data_validation(dv_bal_shock)
    dv_bal_shock.add("B5")

    dv_stress = DataValidation(
        type="list", formula1='"FALSE,TRUE"', allow_blank=False,
    )
    ws_scenarios.add_data_validation(dv_stress)
    dv_stress.add("B6")

    # ==================================================================
    # 5. Charts sheet (placeholder for Phase B3)
    # ==================================================================
    _apply_header_row(ws_charts, ["Charts — Balance & Rate Visualization"], row=1)
    ws_charts.merge_cells("A1:E1")
    ws_charts.cell(row=1, column=1).alignment = Alignment(horizontal="center")
    ws_charts["A3"] = "Charts will populate in Phase B3."
    ws_charts["A3"].font = Font(name="Calibri", italic=True, color="888888", size=11)
    ws_charts["A5"] = "Planned:"
    ws_charts["A5"].font = _LABEL_FONT
    ws_charts["A6"] = "  - Balance over time (line)"
    ws_charts["A7"] = "  - Rate over time (line)"
    ws_charts["A8"] = "  - Shock comparison (dual axis)"
    for r in range(6, 9):
        ws_charts.cell(row=r, column=1).font = _BODY_FONT
    ws_charts.column_dimensions["A"].width = 40

    return wb


# =============================================================================
# Main entry point
# =============================================================================

def build_excel_workbook(
    *,
    mode: Literal["session", "persistent"],
    feature: Literal["snapshot", "simulator", "explain"],
    session_id: str | None = None,
    analysis_id: int | None = None,
    user_id: int | None = None,
    request: Request | None = None,
    # Phase A: allow injected payload for session mode
    _loan: LoanInputs | None = None,
    _scenario: ScenarioConfig | None = None,
    _series: SeriesData | None = None,
) -> str:
    """
    Build and save an Excel workbook for export.

    Args:
        mode: "session" or "persistent"
        feature: "snapshot", "simulator", or "explain"
        session_id: Required for session mode
        analysis_id: Required for persistent mode
        user_id: Required for persistent mode
        request: Starlette Request (for IP + audit)
        _loan, _scenario, _series: Injected payloads (session mode)

    Returns:
        Absolute path to the saved .xlsx file

    Raises:
        ValueError: Missing required args
        PolicyViolation: Policy check failure
    """
    _ensure_app_helpers()

    # Resolve audit metadata
    req_id = getattr(request.state, "request_id", None) if request else None
    ip = _get_client_ip(request) if request else None

    # Audit: requested
    _policy_log_event(
        db=_db,
        user_id=user_id,
        event_kind="export_xlsx_requested",
        details_json=_safe_json_dumps({
            "mode": mode,
            "feature": feature,
            "session_id": session_id,
            "analysis_id": analysis_id,
        }),
        session_id=session_id,
        analysis_id=analysis_id,
        request_id=req_id,
        ip_address=ip,
    )

    try:
        # ---- Policy enforcement ----
        if mode == "persistent":
            if not user_id or not analysis_id:
                raise ValueError("Persistent mode requires user_id and analysis_id")
            _policy_guard({
                "route": "/excel_export/build",
                "mode": "persistent",
                "user_id": user_id,
                "analysis_id": analysis_id,
            })
            # Phase A: persistent parquet loading is a placeholder
            raise NotImplementedError(
                "Persistent-mode Excel export will be implemented in Phase B"
            )

        if mode == "session":
            if not session_id:
                raise ValueError("Session mode requires session_id")

        # ---- Build payload ----
        if _loan and _scenario and _series:
            loan = _loan
            scenario = _scenario
            series = _series
        else:
            # Infer from session data
            from core.database_session_manager import DatabaseSessionManager
            sm = DatabaseSessionManager(ttl_minutes=30)
            sess = sm.get_session(session_id)
            if not sess:
                raise ValueError(f"Session not found or expired: {session_id}")

            df = sess["df"]
            dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
            balances = df["balance"].tolist()
            rates = df["rate"].tolist()

            series = SeriesData(dates=dates, balances=balances, rates=rates)
            loan = LoanInputs(
                principal=balances[0] if balances else 0,
                start_date=dates[0] if dates else "1900-01-01",
                term_months=60,
                rate=float(df["rate"].mean()) * 100 if len(df) > 0 else 5.0,
                payment_frequency="Monthly",
            )
            scenario = ScenarioConfig(
                rate_shock_bps=0,
                balance_shock_pct=0.0,
                stress_toggle=False,
            )

        # ---- Build workbook ----
        wb = _build_skeleton_workbook(loan, scenario, series)

        # ---- Save ----
        exports_dir = Path(__file__).resolve().parent.parent / "exports"
        exports_dir.mkdir(exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_feature = feature.replace("/", "_")
        if session_id:
            short_id = session_id[:8]
        elif analysis_id:
            short_id = str(analysis_id)
        else:
            short_id = "export"
        filename = f"banker_analytics_{safe_feature}_{short_id}_{ts}.xlsx"
        filepath = exports_dir / filename
        wb.save(str(filepath))

        file_size = filepath.stat().st_size
        logger.info(f"Excel export saved: {filepath} ({file_size} bytes)")

        # Audit: success
        _policy_log_event(
            db=_db,
            user_id=user_id,
            event_kind="export_xlsx_success",
            details_json=_safe_json_dumps({
                "filename": filename,
                "file_size": file_size,
                "mode": mode,
                "feature": feature,
            }),
            session_id=session_id,
            analysis_id=analysis_id,
            request_id=req_id,
            ip_address=ip,
        )

        return str(filepath)

    except Exception as e:
        # Audit: failed
        _policy_log_event(
            db=_db,
            user_id=user_id,
            event_kind="export_xlsx_failed",
            details_json=_safe_json_dumps({
                "error": str(e),
                "mode": mode,
                "feature": feature,
            }),
            session_id=session_id,
            analysis_id=analysis_id,
            request_id=req_id,
            ip_address=ip,
        )
        raise
