import asyncio

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.analysis.risk import RiskRequest, calculate_risk


async def main():
    provider = MT5BridgeProvider("http://172.16.204.62:8765")

    try:
        symbol = "XAUUSDm"

        info = await provider.symbol_info(symbol)

        print("=== SYMBOL INFO ===")
        print(info)

        request = RiskRequest(
            symbol=symbol,
            account_equity=1_000.0,
            risk_percent=1.0,
            entry_price=4320.000,
            stop_price=4310.000,
        )

        plan = calculate_risk(
            request=request,
            tick_size=info.tick_size,
            tick_value=info.tick_value,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
        )

        print("\n=== RISK PLAN ===")
        print(f"Symbol          : {plan.symbol}")
        print(f"Equity          : {plan.account_equity}")
        print(f"Risk %          : {plan.risk_percent}%")
        print(f"Risk amount     : {plan.risk_amount}")
        print(f"Entry           : {plan.entry_price}")
        print(f"Stop            : {plan.stop_price}")
        print(f"Stop distance   : {plan.stop_distance}")
        print(f"Tick size       : {plan.tick_size}")
        print(f"Tick value      : {plan.tick_value}")
        print(f"Raw volume      : {plan.raw_volume}")
        print(f"Normalized lot  : {plan.volume}")
        print(f"Estimated loss  : {plan.estimated_loss}")

    finally:
        await provider.aclose()


asyncio.run(main())
