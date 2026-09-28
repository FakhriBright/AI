from typing import Any


_CORE_KEYS = ("symbol", "generated_at_utc", "market_bias", "trade_plan")

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
    return any(hint in text for hint in hints)


def select_chat_context(
    ai_context: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    """
    Deterministic context selection for AI Analyst Chat.

    Does not call an AI classifier. Ensures queries about entry, trend, RSI,
    SL/TP, scenarios, levels, or fundamentals retain all necessary technical
    and level context so quality is strictly maintained.
    """
    text = message.lower()

    selected: dict[str, Any] = {
        key: ai_context[key]
        for key in _CORE_KEYS
        if key in ai_context
    }

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
        # Entry, SL/TP, and scenario queries need levels and MTF structure for context
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

    if include_mtf and "multi_timeframe" in ai_context:
        selected["multi_timeframe"] = ai_context["multi_timeframe"]

    if include_levels and "key_levels" in ai_context:
        selected["key_levels"] = ai_context["key_levels"]

    if include_scenarios and "scenarios" in ai_context:
        selected["scenarios"] = ai_context["scenarios"]

    return selected
