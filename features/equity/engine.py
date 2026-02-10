"""
Equity model engine — computes projected financials, DCF valuation,
sensitivity analysis, and quant metrics from a snapshot + assumptions.
All computations are deterministic and offline.
"""

import logging

logger = logging.getLogger(__name__)

DEFAULT_ASSUMPTIONS = {
    "revenue_cagr": 0.10,
    "cogs_pct": 0.60,
    "sga_pct": 0.15,
    "da_pct": 0.05,
    "tax_rate": 0.21,
    "wacc": 0.10,
    "terminal_growth": 0.03,
    "risk_free_rate": 0.04,
    "equity_risk_premium": 0.05,
    "beta": 1.0,
    "cost_of_debt": 0.05,
    "capex_pct_revenue": 0.08,
    "dso": 30,
    "dio": 45,
    "dpo": 35,
    "projection_years": 5,
}


class EquityModelEngine:
    """Runs deterministic equity valuation model."""

    def run(self, snapshot: dict, assumptions: dict | None = None) -> dict:
        """Run full model pipeline: project financials, compute DCF, sensitivity.

        Args:
            snapshot: Output from EquityDataProvider.get_snapshot()
            assumptions: Override dict (merged with DEFAULT_ASSUMPTIONS)

        Returns:
            Complete outputs dict with projected statements, DCF, sensitivity, quant.
        """
        a = dict(DEFAULT_ASSUMPTIONS)
        if assumptions:
            a.update(assumptions)

        hist = snapshot["historic_financials"]
        bs = snapshot["balance_sheet"]

        # --- Projected Income Statement (5 years) ---
        base_revenue = hist["revenue"][-1]
        proj_years = list(range(
            hist["years"][-1] + 1,
            hist["years"][-1] + 1 + a["projection_years"],
        ))
        proj_revenue = []
        proj_cogs = []
        proj_gross_profit = []
        proj_sga = []
        proj_ebitda = []
        proj_da = []
        proj_ebit = []
        proj_interest = []
        proj_ebt = []
        proj_tax = []
        proj_net_income = []

        rev = base_revenue
        for _ in range(a["projection_years"]):
            rev = round(rev * (1 + a["revenue_cagr"]))
            cogs = round(rev * a["cogs_pct"])
            gp = rev - cogs
            sga = round(rev * a["sga_pct"])
            ebitda = gp - sga
            da = round(rev * a["da_pct"])
            ebit = ebitda - da
            interest = round(bs["debt"][-1] * a["cost_of_debt"])
            ebt = ebit - interest
            tax = round(max(0, ebt) * a["tax_rate"])
            ni = ebt - tax

            proj_revenue.append(rev)
            proj_cogs.append(cogs)
            proj_gross_profit.append(gp)
            proj_sga.append(sga)
            proj_ebitda.append(ebitda)
            proj_da.append(da)
            proj_ebit.append(ebit)
            proj_interest.append(interest)
            proj_ebt.append(ebt)
            proj_tax.append(tax)
            proj_net_income.append(ni)

        projected_income_statement = {
            "years": proj_years,
            "revenue": proj_revenue,
            "cogs": proj_cogs,
            "gross_profit": proj_gross_profit,
            "sga": proj_sga,
            "ebitda": proj_ebitda,
            "da": proj_da,
            "ebit": proj_ebit,
            "interest": proj_interest,
            "ebt": proj_ebt,
            "tax": proj_tax,
            "net_income": proj_net_income,
        }

        # --- Projected Balance Sheet ---
        proj_bs_years = proj_years
        proj_cash = []
        proj_ar = []
        proj_total_current = []
        proj_fixed_assets = []
        proj_total_assets = []
        proj_ap = []
        proj_deferred_rev = []
        proj_total_current_li = []
        proj_debt_vals = []
        proj_total_liabilities = []
        proj_common_stock = []
        proj_retained_earnings = []
        proj_total_equity = []

        prev_cash = bs["cash"][-1]
        prev_ar = bs["ar"][-1]
        prev_fixed = bs["fixed_assets"][-1]
        prev_ap = bs["ap"][-1]
        prev_def_rev = bs["deferred_rev"][-1]
        prev_debt = bs["debt"][-1]
        prev_stock = bs["common_stock"][-1]
        prev_re = bs["retained_earnings"][-1]

        for i in range(a["projection_years"]):
            r = proj_revenue[i]
            c = proj_cogs[i]
            ni = proj_net_income[i]
            da_val = proj_da[i]
            capex = round(r * a["capex_pct_revenue"])

            ar = round(r * a["dso"] / 365)
            ap = round(c * a["dpo"] / 365)
            def_rev = round(r * 0.02)
            fixed = prev_fixed + capex - da_val

            # Net cash flow estimate
            delta_ar = ar - prev_ar
            delta_ap = ap - prev_ap
            delta_def = def_rev - prev_def_rev
            ocf = ni + da_val - delta_ar + delta_ap + delta_def
            cash = prev_cash + ocf - capex

            total_current = cash + ar
            total_assets_val = total_current + fixed
            total_current_li_val = ap + def_rev
            total_li = total_current_li_val + prev_debt
            re = prev_re + ni
            total_eq = prev_stock + re

            proj_cash.append(round(cash))
            proj_ar.append(round(ar))
            proj_total_current.append(round(total_current))
            proj_fixed_assets.append(round(fixed))
            proj_total_assets.append(round(total_assets_val))
            proj_ap.append(round(ap))
            proj_deferred_rev.append(round(def_rev))
            proj_total_current_li.append(round(total_current_li_val))
            proj_debt_vals.append(round(prev_debt))
            proj_total_liabilities.append(round(total_li))
            proj_common_stock.append(round(prev_stock))
            proj_retained_earnings.append(round(re))
            proj_total_equity.append(round(total_eq))

            prev_cash = cash
            prev_ar = ar
            prev_fixed = fixed
            prev_ap = ap
            prev_def_rev = def_rev
            prev_re = re

        projected_balance_sheet = {
            "years": proj_bs_years,
            "cash": proj_cash,
            "ar": proj_ar,
            "total_current": proj_total_current,
            "fixed_assets": proj_fixed_assets,
            "total_assets": proj_total_assets,
            "ap": proj_ap,
            "deferred_rev": proj_deferred_rev,
            "total_current_li": proj_total_current_li,
            "debt": proj_debt_vals,
            "total_liabilities": proj_total_liabilities,
            "common_stock": proj_common_stock,
            "retained_earnings": proj_retained_earnings,
            "total_equity": proj_total_equity,
        }

        # --- Projected Cash Flow ---
        proj_ocf = []
        proj_icf = []
        proj_fcf_vals = []
        proj_ncf = []

        for i in range(a["projection_years"]):
            ni = proj_net_income[i]
            da_val = proj_da[i]
            capex = round(proj_revenue[i] * a["capex_pct_revenue"])

            # Delta working capital
            if i == 0:
                delta_ar = proj_ar[i] - bs["ar"][-1]
                delta_ap = proj_ap[i] - bs["ap"][-1]
                delta_def = proj_deferred_rev[i] - bs["deferred_rev"][-1]
            else:
                delta_ar = proj_ar[i] - proj_ar[i - 1]
                delta_ap = proj_ap[i] - proj_ap[i - 1]
                delta_def = proj_deferred_rev[i] - proj_deferred_rev[i - 1]

            ocf = ni + da_val - delta_ar + delta_ap + delta_def
            icf = -capex
            financing_cf = 0  # No new debt/repayment assumed
            ncf = ocf + icf + financing_cf

            proj_ocf.append(round(ocf))
            proj_icf.append(round(icf))
            proj_fcf_vals.append(round(financing_cf))
            proj_ncf.append(round(ncf))

        projected_cash_flow = {
            "years": proj_years,
            "net_income": proj_net_income,
            "da": proj_da,
            "operating_cf": proj_ocf,
            "investing_cf": proj_icf,
            "financing_cf": proj_fcf_vals,
            "net_cash_flow": proj_ncf,
        }

        # --- UFCF for DCF ---
        ufcf = []
        for i in range(a["projection_years"]):
            nopat = round(proj_ebit[i] * (1 - a["tax_rate"]))
            da_val = proj_da[i]
            capex = round(proj_revenue[i] * a["capex_pct_revenue"])
            if i == 0:
                delta_nwc = (proj_ar[i] - bs["ar"][-1]) - (proj_ap[i] - bs["ap"][-1])
            else:
                delta_nwc = (proj_ar[i] - proj_ar[i - 1]) - (proj_ap[i] - proj_ap[i - 1])
            fcf_val = nopat + da_val - capex - delta_nwc
            ufcf.append(round(fcf_val))

        # --- WACC Calculation ---
        equity_val = snapshot["market_cap"]
        debt_val = max(0, bs["debt"][-1])
        total_capital = equity_val + debt_val
        e_weight = equity_val / total_capital if total_capital > 0 else 1.0
        d_weight = debt_val / total_capital if total_capital > 0 else 0.0
        cost_of_equity = a["risk_free_rate"] + a["beta"] * a["equity_risk_premium"]
        after_tax_cost_of_debt = a["cost_of_debt"] * (1 - a["tax_rate"])
        wacc = e_weight * cost_of_equity + d_weight * after_tax_cost_of_debt

        wacc_calc = {
            "equity_value": equity_val,
            "debt_value": debt_val,
            "cost_of_debt": a["cost_of_debt"],
            "tax_rate": a["tax_rate"],
            "d_weight": round(d_weight, 4),
            "after_tax_cost_of_debt": round(after_tax_cost_of_debt, 4),
            "risk_free_rate": a["risk_free_rate"],
            "equity_risk_premium": a["equity_risk_premium"],
            "beta": a["beta"],
            "e_weight": round(e_weight, 4),
            "cost_of_equity": round(cost_of_equity, 4),
            "wacc": round(wacc, 4),
        }

        # --- DCF Valuation ---
        pv_fcf = []
        for i, fcf_val in enumerate(ufcf):
            pv = fcf_val / ((1 + wacc) ** (i + 1))
            pv_fcf.append(round(pv))

        sum_pv_fcf = sum(pv_fcf)

        # Terminal value: Gordon Growth
        g = a["terminal_growth"]
        if wacc > g:
            terminal_value = round(ufcf[-1] * (1 + g) / (wacc - g))
        else:
            terminal_value = 0

        n = a["projection_years"]
        pv_terminal = round(terminal_value / ((1 + wacc) ** n))

        enterprise_value = sum_pv_fcf + pv_terminal
        cash_val = snapshot["cash"]
        debt_bridge = max(0, bs["debt"][-1])
        minority = snapshot.get("minority_interest", 0)
        equity_value = enterprise_value + cash_val - debt_bridge - minority

        shares = snapshot["shares_outstanding"]
        implied_price = round(equity_value / shares, 2) if shares > 0 else 0

        dcf = {
            "ufcf": ufcf,
            "pv_fcf": pv_fcf,
            "sum_pv_fcf": sum_pv_fcf,
            "terminal_growth": g,
            "wacc_used": round(wacc, 4),
            "terminal_value": terminal_value,
            "pv_terminal": pv_terminal,
            "enterprise_value": enterprise_value,
            "cash": cash_val,
            "debt": debt_bridge,
            "minority_interest": minority,
            "equity_value": equity_value,
            "shares_outstanding": shares,
            "implied_price": implied_price,
        }

        # --- Sensitivity Grid (5x5: WACC x Terminal Growth) ---
        wacc_base = wacc
        g_base = g
        wacc_offsets = [-0.01, -0.005, 0, 0.005, 0.01]
        g_offsets = [-0.01, -0.005, 0, 0.005, 0.01]
        wacc_values = [round(wacc_base + o, 4) for o in wacc_offsets]
        growth_values = [round(g_base + o, 4) for o in g_offsets]

        prices = []
        for w in wacc_values:
            row = []
            for gv in growth_values:
                if w > gv and w > 0:
                    tv = ufcf[-1] * (1 + gv) / (w - gv)
                    pv_tv = tv / ((1 + w) ** n)
                    pv_sum = sum(f / ((1 + w) ** (j + 1)) for j, f in enumerate(ufcf))
                    ev = pv_sum + pv_tv
                    eq = ev + cash_val - debt_bridge - minority
                    price = round(eq / shares, 2) if shares > 0 else 0
                else:
                    price = 0
                row.append(price)
            prices.append(row)

        sensitivity_grid = {
            "wacc_values": wacc_values,
            "growth_values": growth_values,
            "prices": prices,
        }

        # --- Quant Metrics (from snapshot market_data) ---
        md = snapshot["market_data"]
        quant_metrics = {
            "ticker_return": md["returns_1y"],
            "spy_return": md["spy_return_1y"],
            "icln_return": md["icln_return_1y"],
            "ticker_volatility": md["volatility"],
            "spy_volatility": md["spy_volatility"],
            "icln_volatility": md["icln_volatility"],
            "beta": md["beta"],
            "ticker_sharpe": md["sharpe"],
            "spy_sharpe": md["spy_sharpe"],
            "icln_sharpe": md["icln_sharpe"],
            "ticker_max_drawdown": md["max_drawdown"],
            "spy_max_drawdown": md["spy_max_drawdown"],
            "icln_max_drawdown": md["icln_max_drawdown"],
            "correlation_spy": md["correlation_spy"],
            "correlation_icln": md["correlation_icln"],
        }

        return {
            "assumptions": a,
            "projected_income_statement": projected_income_statement,
            "projected_balance_sheet": projected_balance_sheet,
            "projected_cash_flow": projected_cash_flow,
            "dcf": dcf,
            "wacc_calc": wacc_calc,
            "sensitivity_grid": sensitivity_grid,
            "quant_metrics": quant_metrics,
        }
