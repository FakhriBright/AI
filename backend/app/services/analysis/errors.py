"""Human-readable reasons for known market-data failures."""
from app.services.analysis.candles import MarketDataInvalid
from app.services.market_data.base import MarketDataUnavailable


def market_data_error_detail(exc: Exception) -> str | None:
    """Return a readable reason for known data problems, else None."""
    if isinstance(exc, MarketDataInvalid):
        return f"Data market tidak valid: {exc}"
    if isinstance(exc, MarketDataUnavailable):
        return f"Data market (MT5 bridge) tidak tersedia: {exc}"
    if isinstance(exc, ValueError) and "Insufficient candle data" in str(exc):
        return f"Data market belum cukup: {exc}"
    return None
