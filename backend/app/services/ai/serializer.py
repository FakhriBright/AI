from dataclasses import asdict
from typing import Any

from app.services.analysis.context import MultiTimeframeContext
from app.services.analysis.bias import MarketBias
from app.services.analysis.levels import KeyLevels
from app.services.analysis.scenario import ScenarioAnalysis
from app.services.analysis.trade_plan import TradePlan


AI_SWINGS_PER_TIMEFRAME = 8
AI_LEVELS_NEAREST_PER_SIDE = 6
AI_LEVELS_CONFLUENCE_PER_SIDE = 4


def _json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "item"):
        return _json_safe(value.item())

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]

    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))

    return value


def _compact_swings(swings: list[Any]) -> list[dict[str, Any]]:
    recent = swings[-AI_SWINGS_PER_TIMEFRAME:]

    return [
        {
            "time_utc": _json_safe(swing.time_utc),
            "type": swing.type,
            "label": swing.label,
            "price": swing.price,
        }
        for swing in recent
    ]


def _compact_timeframe(tf: Any) -> dict[str, Any]:
    return {
        "timeframe": tf.timeframe,
        "price": tf.price,
        "trend": tf.trend,
        "structure": tf.structure,
        "ema_alignment": tf.ema_alignment,
        "ema20": tf.ema20,
        "ema50": tf.ema50,
        "ema200": tf.ema200,
        "rsi14": tf.rsi14,
        "macd": tf.macd,
        "macd_signal": tf.macd_signal,
        "macd_hist": tf.macd_hist,
        "atr14": tf.atr14,
        "reasons": list(tf.reasons),
        "swings": _compact_swings(tf.swings),
    }


def _compact_multi_timeframe(
    context: MultiTimeframeContext,
) -> dict[str, Any]:
    return {
        timeframe: _compact_timeframe(tf)
        for timeframe, tf in context.timeframes.items()
    }


def _level_distance(
    level: dict[str, Any],
    current_price: float,
) -> float:
    return abs(
        float(level.get("price", current_price)) - current_price
    )


def _compact_levels(levels: KeyLevels) -> dict[str, Any]:
    data = _json_safe(levels)
    current_price = float(data["current_price"])

    def compact_side(
        items: list[dict[str, Any]],
        level_type: str,
    ) -> list[dict[str, Any]]:
        if not items:
            return []

        nearest = sorted(
            items,
            key=lambda level: _level_distance(
                level,
                current_price,
            ),
        )[:AI_LEVELS_NEAREST_PER_SIDE]

        confluence = sorted(
            items,
            key=lambda level: (
                -int(level.get("touches", 0)),
                -len(level.get("timeframes", [])),
                _level_distance(level, current_price),
            ),
        )[:AI_LEVELS_CONFLUENCE_PER_SIDE]

        combined = {
            str(level.get("price")): level
            for level in [*nearest, *confluence]
        }

        result = []

        for level in combined.values():
            result.append(
                {
                    "price": level.get("price"),
                    "low": level.get("low"),
                    "high": level.get("high"),
                    "level_type": level.get(
                        "level_type",
                        level_type,
                    ),
                    "timeframes": level.get(
                        "timeframes",
                        [],
                    ),
                    "touches": level.get(
                        "touches",
                        0,
                    ),
                }
            )

        return sorted(
            result,
            key=lambda level: _level_distance(
                level,
                current_price,
            ),
        )

    return {
        "symbol": data.get("symbol"),
        "current_price": current_price,
        "supports": compact_side(
            data.get("supports", []),
            "support",
        ),
        "resistances": compact_side(
            data.get("resistances", []),
            "resistance",
        ),
    }


def _compact_trade_plan(
    trade_plan: TradePlan,
) -> dict[str, Any]:
    """
    Compact representation for AI reasoning.

    The full technical_context and levels_context remain inside
    the deterministic TradePlan object for engine/dashboard use.
    They are omitted here because the same information is already
    provided separately through multi_timeframe and key_levels.
    """
    return {
        "symbol": trade_plan.symbol,
        "scenario_name": trade_plan.scenario_name,
        "direction": trade_plan.direction,
        "status": trade_plan.status,
        "entry_price": trade_plan.entry_price,
        "stop_price": trade_plan.stop_price,
        "stop_distance": trade_plan.stop_distance,
        "risk_percent": trade_plan.risk_percent,
        "risk_amount": trade_plan.risk_amount,
        "volume": trade_plan.volume,
        "estimated_loss": trade_plan.estimated_loss,
        "confirmation_type": trade_plan.confirmation_type,
        "stop_method": trade_plan.stop_method,
        "market_bias": trade_plan.market_bias,
        "htf_bias": trade_plan.htf_bias,
        "intraday_bias": trade_plan.intraday_bias,
        "entry_bias": trade_plan.entry_bias,
        "conflicts": list(trade_plan.conflicts),
        "reasons": list(trade_plan.reasons),
        "warnings": list(trade_plan.warnings),
    }


def build_ai_context(
    context: MultiTimeframeContext,
    bias: MarketBias,
    levels: KeyLevels,
    scenarios: ScenarioAnalysis,
    trade_plan: TradePlan,
) -> dict[str, Any]:
    return {
        "symbol": context.symbol,
        "generated_at_utc": _json_safe(
            context.generated_at_utc
        ),
        "market_bias": _json_safe(bias),
        "multi_timeframe": _compact_multi_timeframe(
            context
        ),
        "key_levels": _compact_levels(levels),
        "scenarios": _json_safe(scenarios),
        "trade_plan": _compact_trade_plan(
            trade_plan
        ),
    }
