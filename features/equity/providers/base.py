"""
Abstract base class for equity data providers.
"""

from abc import ABC, abstractmethod


class EquityDataProvider(ABC):
    """Abstract interface for fetching equity snapshot data."""

    @abstractmethod
    def get_snapshot(self, ticker: str) -> dict:
        """Returns structured snapshot dict with financials + market data.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL")

        Returns:
            Dict containing company_name, ticker, sector, exchange,
            current_price, market_cap, historic_financials,
            balance_sheet, market_data, strategy, etc.
        """
        ...
