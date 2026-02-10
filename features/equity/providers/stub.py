"""
Stub equity data provider — deterministic, offline, zero network calls.
Returns realistic financial data for any ticker.
"""

from features.equity.providers.base import EquityDataProvider


STUB_SNAPSHOT = {
    "company_name": "Apple Inc.",
    "ticker": "AAPL",
    "sector": "Technology",
    "exchange": "NASDAQ",
    "current_price": 185.00,
    "market_cap": 2_850_000,
    "enterprise_value": 2_820_000,
    "high_52w": 199.62,
    "low_52w": 143.90,
    "shares_outstanding": 15_405,
    "net_debt": -30_000,
    "cash": 62_000,
    "minority_interest": 0,
    "historic_financials": {
        "years": [2021, 2022, 2023],
        "revenue":       [365_817, 394_328, 383_285],
        "cogs":          [212_981, 223_546, 214_137],
        "gross_profit":  [152_836, 170_782, 169_148],
        "sga":           [43_887,  51_334,  54_847],
        "ebitda":        [120_233, 130_541, 125_820],
        "da":            [11_284,  11_104,  11_519],
        "ebit":          [108_949, 119_437, 114_301],
        "interest":      [2_645,   2_931,   3_933],
        "ebt":           [109_207, 119_103, 113_736],
        "tax":           [14_527,  19_300,  16_741],
        "net_income":    [94_680,  99_803,  96_995],
    },
    "balance_sheet": {
        "years": [2020, 2021, 2022, 2023],
        "cash":             [38_016, 34_940, 23_646, 29_965],
        "ar":               [16_120, 26_278, 28_184, 29_508],
        "total_current":    [143_713, 134_836, 135_405, 143_566],
        "fixed_assets":     [36_766, 39_440, 42_117, 43_715],
        "accum_depr":       [0, 0, 0, 0],
        "total_assets":     [323_888, 351_002, 352_755, 352_583],
        "ap":               [42_296, 54_763, 64_115, 62_611],
        "deferred_rev":     [7_612, 7_612, 7_912, 8_061],
        "total_current_li": [105_392, 125_481, 153_982, 145_308],
        "debt":             [112_436, 124_719, 120_069, 111_088],
        "total_liabilities": [258_549, 287_912, 302_083, 290_437],
        "common_stock":     [50_779, 57_365, 64_849, 73_812],
        "retained_earnings": [-406, 5_562, -3_068, -214],
        "total_equity":     [65_339, 63_090, 50_672, 62_146],
    },
    "market_data": {
        "returns_1y": 0.23,
        "returns_3y": 0.45,
        "volatility": 0.28,
        "beta": 1.19,
        "sharpe": 1.05,
        "max_drawdown": -0.178,
        "correlation_spy": 0.92,
        "correlation_icln": 0.35,
        "spy_return_1y": 0.18,
        "spy_volatility": 0.15,
        "spy_sharpe": 0.95,
        "spy_max_drawdown": -0.105,
        "icln_return_1y": -0.08,
        "icln_volatility": 0.32,
        "icln_sharpe": -0.10,
        "icln_max_drawdown": -0.35,
    },
    "strategy": {
        "porter_scores": {
            "new_entrants": 2,
            "suppliers": 3,
            "buyers": 4,
            "substitutes": 2,
            "rivalry": 4,
        }
    },
}


class StubEquityProvider(EquityDataProvider):
    """Deterministic stub provider for offline development and testing."""

    def get_snapshot(self, ticker: str) -> dict:
        """Returns deterministic stub data. Ticker is embedded but data is fixed."""
        snapshot = dict(STUB_SNAPSHOT)
        snapshot["ticker"] = ticker.upper()
        if ticker.upper() != "AAPL":
            snapshot["company_name"] = f"{ticker.upper()} Corp."
        return snapshot
