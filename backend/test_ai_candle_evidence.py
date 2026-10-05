"""Offline test: deterministic candle + pattern evidence reaches the AI context.

No MT5 bridge, no API keys. A fake provider supplies synthetic candles that
include a deliberately FORMING (unclosed) last bar per timeframe.
"""
import asyncio
import json
import random
from datetime import datetime, timedelta, timezone

from app.services.analysis.candles import TIMEFRAME_MINUTES
from app.services.analysis.pipeline import analyze_symbol
from app.services.ai.serializer import AI_CANDLES_PER_TIMEFRAME, dumps_compact
from app.services.market_data.base import Candle

TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
FORMING_MARK = 9999.0  # impossible price used to tag the forming candle


def _floor(now: datetime, minutes: int) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    step = minutes * 60
    secs = int((now - epoch).total_seconds())
    return epoch + timedelta(seconds=secs - secs % step)


def _series(timeframe: str, count: int) -> list[Candle]:
    minutes = TIMEFRAME_MINUTES[timeframe]
    now = datetime.now(timezone.utc)
    forming_open = _floor(now, minutes)
    rng = random.Random(f"seed-{timeframe}")
    price = 4150.0
    out: list[Candle] = []
    for i in range(count - 1, 0, -1):
        t = forming_open - timedelta(minutes=minutes * i)
        o = price
        c = o + rng.uniform(-1.0, 1.0)
        h = max(o, c) + rng.uniform(0.1, 0.6)
        l = min(o, c) - rng.uniform(0.1, 0.6)
        out.append(Candle(time_utc=t, open=o, high=h, low=l, close=c, tick_volume=100 + i))
        price = c
    # Last CLOSED candle: bullish pin bar (small body, long lower wick).
    last = out[-1]
    o = price
    out[-1] = Candle(
        time_utc=last.time_utc, open=o, high=o + 0.25, low=o - 3.0,
        close=o + 0.15, tick_volume=777,
    )
    # Forming candle (must never reach the AI).
    out.append(Candle(
        time_utc=forming_open, open=FORMING_MARK, high=FORMING_MARK,
        low=FORMING_MARK, close=FORMING_MARK, tick_volume=1,
    ))
    return out


class FakeProvider:
    async def get_candles(self, symbol, timeframe, count=300, **_):
        return _series(timeframe, max(count, 300))[-count:] if count >= 2 else _series(timeframe, 300)[-count:]

    async def account_info(self):  # pragma: no cover - risk_percent=None
        raise RuntimeError("not used")

    async def symbol_info(self, symbol):  # pragma: no cover
        raise RuntimeError("not used")


def _run():
    return asyncio.run(
        analyze_symbol("XAUUSDm", FakeProvider(), ai_service=None, run_ai=False)
    )


def test_candles_and_patterns_reach_ai_context():
    result = _run()
    mtf = result.ai_context["multi_timeframe"]
    assert list(mtf) == TIMEFRAMES
    for tf in TIMEFRAMES:
        assert "candles" in mtf[tf] and "patterns" in mtf[tf]
        candles = mtf[tf]["candles"]
        assert 0 < len(candles) <= AI_CANDLES_PER_TIMEFRAME
        assert set(candles[0]) == {
            "time_utc", "open", "high", "low", "close", "tick_volume",
        }
        assert candles[-1]["tick_volume"] == 777  # last CLOSED candle
        for p in mtf[tf]["patterns"]:
            assert set(p) == {
                "name", "direction", "strength", "reasons", "impact", "confirmation",
            }


def test_pin_bar_from_deterministic_engine():
    mtf = _run().ai_context["multi_timeframe"]
    for tf in TIMEFRAMES:
        names = {(p["name"], p["direction"]) for p in mtf[tf]["patterns"]}
        assert ("pin_bar", "bullish") in names, tf
        assert ("hammer", "bullish") in names, tf  # alias is forwarded


def test_forming_candle_never_sent():
    result = _run()
    # Evidence section only. NOTE: trade_plan.reasons may quote the forming M1
    # candle via the pre-existing confirm_scenario(latest_candle) path.
    payload = dumps_compact(result.ai_context["multi_timeframe"])
    assert str(FORMING_MARK) not in payload
    json.loads(dumps_compact(result.ai_context))  # whole context JSON-safe
    for tf in TIMEFRAMES:
        snap = result.snapshot.timeframes[tf]
        assert all(c.open != FORMING_MARK for c in snap.candles)


def test_scenario_behaviour_not_activated_by_new_fields():
    # scenario.py reads getattr(tf, "candles", []); that must stay empty.
    ctx = _run().context
    assert all(not hasattr(tf, "candles") for tf in ctx.timeframes.values())


if __name__ == "__main__":
    r = _run()
    print(json.dumps(r.ai_context["multi_timeframe"]["M5"], indent=2, default=str)[:3500])
    print("payload chars (full ai_context):", len(dumps_compact(r.ai_context)))
