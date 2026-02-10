"""
Equity Research routes (Milestone 5 - E1 Foundation).
All 5 endpoints: landing, snapshot, run-model, export-xlsx, report-draft.
"""

import json
import logging
import uuid
from datetime import datetime

from fastapi import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from starlette.requests import Request

from features.equity.providers.stub import StubEquityProvider
from features.equity.engine import EquityModelEngine
from features.equity.excel.builder import EquityWorkbookBuilder
from features.equity.db import (
    insert_equity_snapshot,
    get_equity_snapshot,
    insert_equity_model_run,
    get_equity_model_run,
)

logger = logging.getLogger(__name__)

# Module-level singletons
_provider = StubEquityProvider()
_engine = EquityModelEngine()
_builder = EquityWorkbookBuilder(exports_dir="exports")


def register_equity_routes(app, templates, db):
    """Register all equity routes on the FastAPI app.

    Args:
        app: FastAPI application instance
        templates: Jinja2Templates instance
        db: Database instance
    """

    @app.get("/equity", response_class=HTMLResponse)
    async def equity_landing(request: Request):
        """Render equity research landing page."""
        logger.info("GET /equity")
        return templates.TemplateResponse(
            "equity_landing.html",
            {"request": request},
        )

    @app.post("/equity/snapshot")
    async def create_equity_snapshot(request: Request):
        """Create an equity snapshot for the given ticker."""
        try:
            form_data = await request.form()
            ticker = form_data.get("ticker", "").strip().upper()

            if not ticker:
                raise HTTPException(status_code=400, detail="Ticker is required")

            logger.info(f"POST /equity/snapshot: ticker={ticker}")
            logger.info(f"Audit: equity_snapshot_requested ticker={ticker}")

            # Get snapshot from stub provider (zero network calls)
            snapshot_data = _provider.get_snapshot(ticker)

            snapshot_id = str(uuid.uuid4())
            asof_date = datetime.now().strftime("%Y-%m-%d")
            snapshot_data["asof_date"] = asof_date

            # Persist to DB
            insert_equity_snapshot(
                db,
                snapshot_id=snapshot_id,
                ticker=ticker,
                asof_date=asof_date,
                raw_json=json.dumps(snapshot_data),
            )

            logger.info(f"Audit: equity_snapshot_success snapshot_id={snapshot_id}")

            return JSONResponse({
                "snapshot_id": snapshot_id,
                "ticker": ticker,
                "asof_date": asof_date,
            })

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Audit: equity_snapshot_failed error={e}")
            raise HTTPException(status_code=500, detail=f"Snapshot creation failed: {str(e)}")

    @app.post("/equity/{snapshot_id}/run-model")
    async def run_equity_model(request: Request, snapshot_id: str):
        """Run the equity model on a snapshot."""
        try:
            logger.info(f"POST /equity/{snapshot_id}/run-model")
            logger.info(f"Audit: equity_model_run_requested snapshot_id={snapshot_id}")

            # Load snapshot
            snap_row = get_equity_snapshot(db, snapshot_id)
            if not snap_row:
                raise HTTPException(status_code=404, detail="Snapshot not found")

            snapshot_data = json.loads(snap_row["raw_json"])

            # Run model engine (deterministic, offline)
            outputs = _engine.run(snapshot_data)

            model_run_id = str(uuid.uuid4())

            # Persist model run
            insert_equity_model_run(
                db,
                model_run_id=model_run_id,
                snapshot_id=snapshot_id,
                assumptions_json=json.dumps(outputs["assumptions"]),
                outputs_json=json.dumps(outputs),
            )

            logger.info(f"Audit: equity_model_run_success model_run_id={model_run_id}")

            return JSONResponse({
                "model_run_id": model_run_id,
                "snapshot_id": snapshot_id,
            })

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Audit: equity_model_run_failed error={e}")
            raise HTTPException(status_code=500, detail=f"Model run failed: {str(e)}")

    @app.post("/equity/{model_run_id}/export-xlsx")
    async def export_equity_xlsx(request: Request, model_run_id: str):
        """Generate and return the equity research Excel workbook."""
        try:
            logger.info(f"POST /equity/{model_run_id}/export-xlsx")
            logger.info(f"Audit: equity_export_requested model_run_id={model_run_id}")

            # Load model run
            run_row = get_equity_model_run(db, model_run_id)
            if not run_row:
                raise HTTPException(status_code=404, detail="Model run not found")

            outputs = json.loads(run_row["outputs_json"])

            # Load associated snapshot
            snap_row = get_equity_snapshot(db, run_row["snapshot_id"])
            if not snap_row:
                raise HTTPException(status_code=404, detail="Snapshot not found")

            snapshot_data = json.loads(snap_row["raw_json"])

            # Build workbook
            filepath = _builder.build(
                snapshot=snapshot_data,
                outputs=outputs,
                model_run_id=model_run_id[:8],
            )

            ticker = snapshot_data["ticker"]
            logger.info(f"Audit: equity_export_success model_run_id={model_run_id} path={filepath}")

            return FileResponse(
                path=filepath,
                filename=f"equity_research_{ticker}.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Audit: equity_export_failed error={e}")
            raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

    @app.get("/equity/{model_run_id}/report-draft")
    async def get_report_draft(request: Request, model_run_id: str):
        """Generate a narrative report draft from model outputs."""
        try:
            logger.info(f"GET /equity/{model_run_id}/report-draft")
            logger.info(f"Audit: equity_report_requested model_run_id={model_run_id}")

            # Load model run
            run_row = get_equity_model_run(db, model_run_id)
            if not run_row:
                raise HTTPException(status_code=404, detail="Model run not found")

            outputs = json.loads(run_row["outputs_json"])

            # Load snapshot for company info
            snap_row = get_equity_snapshot(db, run_row["snapshot_id"])
            if not snap_row:
                raise HTTPException(status_code=404, detail="Snapshot not found")

            snapshot_data = json.loads(snap_row["raw_json"])

            # Generate narrative
            report_text = _generate_report_narrative(snapshot_data, outputs)

            logger.info(f"Audit: equity_report_success model_run_id={model_run_id}")

            return JSONResponse({
                "model_run_id": model_run_id,
                "report_text": report_text,
            })

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Report draft error: {e}")
            raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


def _generate_report_narrative(snapshot: dict, outputs: dict) -> str:
    """Generate a template-based narrative report from model outputs."""
    dcf = outputs["dcf"]
    wacc_calc = outputs["wacc_calc"]
    a = outputs["assumptions"]
    hist = snapshot["historic_financials"]
    qm = outputs["quant_metrics"]

    ticker = snapshot["ticker"]
    company = snapshot["company_name"]
    current = snapshot["current_price"]
    implied = dcf["implied_price"]
    upside = ((implied - current) / current * 100) if current else 0

    rev_latest = hist["revenue"][-1]
    ni_latest = hist["net_income"][-1]
    ebitda_latest = hist["ebitda"][-1]

    lines = [
        f"Equity Research Report: {company} ({ticker})",
        f"{'=' * 50}",
        "",
        f"Executive Summary",
        f"-" * 20,
        f"{company} currently trades at ${current:.2f} per share. Our DCF analysis, "
        f"using a WACC of {wacc_calc['wacc']:.1%} and terminal growth rate of {a['terminal_growth']:.1%}, "
        f"yields an implied share price of ${implied:.2f}, representing "
        f"{'upside' if upside >= 0 else 'downside'} of {abs(upside):.1f}%.",
        "",
        f"Financial Highlights",
        f"-" * 20,
        f"- LTM Revenue: ${rev_latest:,.0f}M",
        f"- LTM EBITDA: ${ebitda_latest:,.0f}M (margin: {ebitda_latest/rev_latest:.1%})",
        f"- LTM Net Income: ${ni_latest:,.0f}M",
        f"- Projected Revenue CAGR: {a['revenue_cagr']:.1%}",
        "",
        f"Valuation",
        f"-" * 20,
        f"- Enterprise Value: ${dcf['enterprise_value']:,.0f}M",
        f"- Equity Value: ${dcf['equity_value']:,.0f}M",
        f"- Terminal Value represents {dcf['pv_terminal']/(dcf['enterprise_value'] or 1):.0%} of total EV",
        "",
        f"Risk Metrics",
        f"-" * 20,
        f"- Beta (vs SPY): {qm['beta']:.2f}",
        f"- 1Y Volatility: {qm['ticker_volatility']:.1%}",
        f"- Sharpe Ratio: {qm['ticker_sharpe']:.2f}",
        f"- Max Drawdown: {qm['ticker_max_drawdown']:.1%}",
        "",
        f"Key Assumptions",
        f"-" * 20,
        f"- Revenue CAGR: {a['revenue_cagr']:.1%}",
        f"- COGS as % of Revenue: {a['cogs_pct']:.1%}",
        f"- WACC: {wacc_calc['wacc']:.2%} (Cost of Equity: {wacc_calc['cost_of_equity']:.2%})",
        f"- Terminal Growth: {a['terminal_growth']:.1%}",
    ]

    return "\n".join(lines)
