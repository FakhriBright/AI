import re
from typing import Any

from app.services.ai.desk import (
    build_desk_brief,
    chat_context_max_chars,
    slim_bias,
    slim_levels,
    slim_multi_timeframe,
    slim_scenarios,
    shrink_to_budget,
    slim_trade_plan,
)

_CORE_KEYS = ("symbol", "generated_at_utc")

_TIMEFRAME_HINTS = (
    "h4",
    "d1",
    "h1",
    "m30",
    "m15",
    "m5",
    "m1",
    "timeframe",
    "multi-time",
    "multi time",
    "mtf",
    "htf",
    "intraday",
    "higher time",
    "lower time",
    "jelaskan kondisi",
    "dari h",
    "until m",
    "sampai m",
    "ema",
    "rsi",
    "macd",
    "atr",
    "struktur",
    "structure",
    "trend",
    "swing",
    "indikator",
    "indicator",
)

_LEVEL_HINTS = (
    "support",
    "resistance",
    "level",
    "zona",
    "zone",
    "liquidity",
    "likuiditas",
    "s/r",
    "sr",
)

_SCENARIO_HINTS = (
    "scenario",
    "skenario",
    "setup",
    "trigger",
    "invalid",
    "konfirmasi",
    "confirm",
    "entry",
    "stop",
    "sl",
    "tp",
    "stop loss",
    "take profit",
    "target",
    "risk",
    "lot",
    "volume",
    "trade plan",
    "rencana",
)

_FUNDAMENTAL_HINTS = (
    "fundamental",
    "news",
    "berita",
    "sentimen",
    "sentiment",
    "event",
    "calendar",
    "kalender",
    "nfp",
    "cpi",
    "fomc",
    "suku bunga",
    "interest rate",
)

_FULL_HINTS = (
    "analis",
    "analys",
    "summar",
    "ringkas",
    "overall",
    "keseluruhan",
    "full",
    "lengkap",
    "confluence",
    "konfluen",
    "explain",
    "jelaskan",
)

_BIAS_HINTS = (
    "bias",
    "mixed",
    "conflict",
    "konflik",
    "bullish",
    "bearish",
    "neutral",
)


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    for hint in hints:
        if len(hint) <= 3:
            # short hints (sl, tp, sr, ema...) must be whole words
            if re.search(rf"(?<![a-z0-9]){re.escape(hint)}(?![a-z0-9])", text):
                return True
        elif hint in text:
            return True
    return False


def select_chat_context(
    ai_context: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    """
    Deterministic, token-efficient context for AI Analyst Chat.

    Always sends the desk brief (closed candles + collapsed patterns + the
    desk each one routes to + entry gate + conditional setups). Sections are
    slimmed: candle tails instead of 200+ bars, nearest levels only, no
    duplicated trade-plan fields. No AI classifier is called.
    """
    text = message.lower()

    selected: dict[str, Any] = {
        key: ai_context[key]
        for key in _CORE_KEYS
        if key in ai_context
    }
    if "market_bias" in ai_context:
        selected["market_bias"] = slim_bias(ai_context["market_bias"])
    if "trade_plan" in ai_context:
        selected["trade_plan"] = slim_trade_plan(ai_context["trade_plan"])

    include_mtf = False
    include_levels = False
    include_scenarios = False

    if (
        _contains_any(text, _FULL_HINTS)
        or _contains_any(text, _FUNDAMENTAL_HINTS)
        or len(message.strip()) > 120
    ):
        include_mtf = True
        include_levels = True
        include_scenarios = True

    if _contains_any(text, _SCENARIO_HINTS):
        include_scenarios = True
        include_levels = True
        include_mtf = True

    if _contains_any(text, _TIMEFRAME_HINTS):
        include_mtf = True
        include_levels = True

    if _contains_any(text, _LEVEL_HINTS):
        include_levels = True
        include_mtf = True

    if _contains_any(text, _BIAS_HINTS):
        include_mtf = True

    if not include_mtf and not include_levels and not include_scenarios:
        include_mtf = True
        include_levels = True
        include_scenarios = True

    selected["desk"] = build_desk_brief(ai_context)

    if include_mtf and "multi_timeframe" in ai_context:
        selected["multi_timeframe"] = slim_multi_timeframe(
            ai_context["multi_timeframe"], "chat"
        )

    if include_levels and "key_levels" in ai_context:
        selected["key_levels"] = slim_levels(ai_context["key_levels"], 3)

    if include_scenarios and "scenarios" in ai_context:
        selected["scenarios"] = slim_scenarios(ai_context)

    return shrink_to_budget(selected, chat_context_max_chars())
