import asyncio
from datetime import datetime, timezone

from app.services.market_data.mt5_bridge import MT5BridgeProvider
from app.services.technical.indicators import ema, rsi, macd, atr
from app.services.technical.structure import find_swings, classify_structure
from app.services.technical.trend import analyze_trend

from app.services.analysis.snapshot import (
    AnalysisSnapshot,
    IndicatorSnapshot,
    SwingSnapshot,
    StructureSnapshot,
    TimeframeSnapshot,
    TrendSnapshot,
)


TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


async def build_analysis_snapshot(
    provider: MT5BridgeProvider,
    symbol: str,
    count: int = 300,
) -> AnalysisSnapshot:

    snapshot = AnalysisSnapshot(
        symbol=symbol,
        generated_at_utc=datetime.now(timezone.utc),
    )

    for timeframe in TIMEFRAMES:

        candles = await provider.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            count=count,
        )

        if len(candles) < 200:
            raise ValueError(
                f"Insufficient candle data for {symbol} {timeframe}: "
                f"{len(candles)} candles"
            )

        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        times = [c.time_utc for c in candles]

        ema20_value = ema(closes, 20)[-1]
        ema50_value = ema(closes, 50)[-1]
        ema200_value = ema(closes, 200)[-1]

        rsi_value = rsi(closes, 14)[-1]

        macd_values = macd(closes, 12, 26, 9)

        macd_value = macd_values[0][-1]
        macd_signal_value = macd_values[1][-1]
        macd_hist_value = macd_values[2][-1]

        atr_value = atr(
            highs,
            lows,
            closes,
            14,
        )[-1]

        swings = find_swings(
            highs=highs,
            lows=lows,
            times=times,
            lookback=3,
        )

        structure_direction = classify_structure(swings)

        trend = analyze_trend(
            price=closes[-1],
            ema20=ema20_value,
            ema50=ema50_value,
            ema200=ema200_value,
            structure=structure_direction,
        )

        recent_swings = [
            SwingSnapshot(
                time_utc=swing.time_utc,
                type=swing.type,
                label=swing.label,
                price=swing.price,
            )
            for swing in swings[-10:]
        ]

        indicator_snapshot = IndicatorSnapshot(
            ema20=ema20_value,
            ema50=ema50_value,
            ema200=ema200_value,
            rsi14=rsi_value,
            macd=macd_value,
            macd_signal=macd_signal_value,
            macd_hist=macd_hist_value,
            atr14=atr_value,
        )

        structure_snapshot = StructureSnapshot(
            direction=structure_direction,
            recent_swings=recent_swings,
        )

        trend_snapshot = TrendSnapshot(
            direction=trend.direction,
            ema_alignment=trend.ema_alignment,
            reasons=trend.reasons,
        )

        timeframe_snapshot = TimeframeSnapshot(
            timeframe=timeframe,
            candle_time_utc=candles[-1].time_utc,
            price=closes[-1],
            indicators=indicator_snapshot,
            structure=structure_snapshot,
            trend=trend_snapshot,
        )

        snapshot.timeframes[timeframe] = timeframe_snapshot

    return snapshot


async def main():
    provider = MT5BridgeProvider(
        "http://172.16.204.62:8765"
    )

    try:
        snapshot = await build_analysis_snapshot(
            provider=provider,
            symbol="EURUSDm",
            count=300,
        )

        print("\n=== ANALYSIS SNAPSHOT ===")
        print(f"SYMBOL: {snapshot.symbol}")
        print(f"GENERATED: {snapshot.generated_at_utc}")

        for timeframe, data in snapshot.timeframes.items():

            print(f"\n--- {timeframe} ---")
            print(f"TIME      : {data.candle_time_utc}")
            print(f"PRICE     : {data.price}")
            print(f"EMA20     : {data.indicators.ema20}")
            print(f"EMA50     : {data.indicators.ema50}")
            print(f"EMA200    : {data.indicators.ema200}")
            print(f"RSI14     : {data.indicators.rsi14}")
            print(f"MACD      : {data.indicators.macd}")
            print(f"MACD SIG  : {data.indicators.macd_signal}")
            print(f"MACD HIST : {data.indicators.macd_hist}")
            print(f"ATR14     : {data.indicators.atr14}")
            print(f"STRUCTURE : {data.structure.direction}")
            print(f"TREND     : {data.trend.direction}")
            print(f"EMA ALIGN : {data.trend.ema_alignment}")

            print("SWINGS:")

            for swing in data.structure.recent_swings[-5:]:
                print(
                    f"  {swing.time_utc} | "
                    f"{swing.type} | "
                    f"{swing.label or '-'} | "
                    f"{swing.price}"
                )

    finally:
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
