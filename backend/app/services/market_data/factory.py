from functools import lru_cache

from app.core.config import settings
from app.services.market_data.base import MarketDataProvider
from app.services.market_data.mt5_bridge import MT5BridgeProvider


@lru_cache
def get_market_data_provider() -> MarketDataProvider:
    """
    Single place that knows the mapping from config value -> implementation.
    Adding a new provider later means adding a branch here, not touching any
    caller (routes/services all depend on the MarketDataProvider ABC).
    """
    if settings.market_data_provider == "mt5_bridge":
        return MT5BridgeProvider(
            base_url=settings.mt5_bridge_url,
            timeout_seconds=settings.mt5_bridge_timeout_seconds,
        )
    raise ValueError(f"Unknown MARKET_DATA_PROVIDER: {settings.market_data_provider}")
