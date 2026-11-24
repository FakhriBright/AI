"""Chat-to-chart: turn one chat exchange into chart commands, without an LLM.

The AI reply is produced by the existing single chat call. This module then
maps (a) the trader's question intent and (b) the prices the reply quotes onto
overlays the engine already produced (see overlays.py). Annotations it creates
use engine prices only: scenario invalidation, current price, and the nearest
engine zone. A position box is never drawn here; the trade-plan layer already
shows one only when the entry gate allows it.
"""

import logging
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.chart import ChartOverlay
from app.services.ai.answer_audit import _NUMBER, _tolerance
from app.services.ai.desk import _scenario_items, build_entry_gate

logger = logging.getLogger(__name__)

MAX_HIGHLIGHTS = 10

_INTENTS: dict[str, tuple[str, ...]] = {
    "clear": ("hapus gambar", "hapus anotasi", "bersihkan chart", "clear drawing", "clear chart", "clear annotation"),
    "liquidity": ("likuid", "liquidity", "bsl", "ssl", "sweep", "stop hunt", "equal high", "equal low",
                  "eqh", "eql", "diincar"),
    "structure": ("kenapa", "mengapa", "why", "alasan", "struktur", "structure", "bos", "choch", "mss"),
    "pullback": ("pullback", "tunggu", "wait", "retest", "langsung"),
    "invalidation": ("invalid", "batal"),
    "setup": ("setup", "entry", "sell", "buy", "jual", "beli", "take profit", "stop loss", "risk reward",
              " tp", " sl", " rr"),
    "fvg": ("fvg", "imbalance", "fair value"),
    "order_blocks": ("order block", " ob ", "supply", "demand"),
    "sr": ("support", "resisten", "resistance", "level"),
    "premium_discount": ("premium", "discount", "diskon", "equilibrium"),
    "trendline": ("trendline", "garis tren", "trend line"),
}

_INTENT_LAYERS = {
    "liquidity": ("liquidity",),
    "structure": ("structure", "trendline"),
    "pullback": ("sr", "order_blocks", "fvg"),
    "invalidation": ("trade_plan",),
    "setup": ("trade_plan",),
    "fvg": ("fvg",),
    "order_blocks": ("order_blocks",),
    "sr": ("sr",),
    "premium_discount": ("premium_discount",),
    "trendline": ("trendline",),
}

_LIVE_STATUSES = {"active", "confirmed", "candidate", "waiting"}


def detect_intents(message: str) -> list[str]:
    text = f" {message.lower()} "
    return [name for name, hints in _INTENTS.items() if any(h in text for h in hints)]


def _explicit_direction(message: str) -> str | None:
    text = message.lower()
    if any(w in text for w in ("bearish", "sell", "jual", "turun", "short")):
        return "bearish"
    if any(w in text for w in ("bullish", "buy", "beli", "naik", "long")):
        return "bullish"
    return None


def _bias_direction(ai_context: dict[str, Any]) -> str | None:
    overall = str((ai_context.get("market_bias") or {}).get("overall") or "").lower()
    return overall if overall in ("bullish", "bearish") else None


_TF_TOKEN = re.compile(r"\b(M1|M5|M15|M30|H1|H4|D1)\b")


def _prices(overlay: dict[str, Any]) -> list[float]:
    values = [overlay.get(k) for k in ("price", "price_low", "price_high", "entry", "stop", "target")]
    values += [p.get("price") for p in overlay.get("points") or []]
    return [float(v) for v in values if isinstance(v, (int, float))]


def _distance(overlay: dict[str, Any], price: float | None) -> float:
    prices = _prices(overlay)
    if price is None or not prices:
        return float("inf")
    return min(abs(p - price) for p in prices)


def _overlay(**fields: Any) -> dict[str, Any] | None:
    try:
        return ChartOverlay(**fields).model_dump(exclude_none=True)
    except ValidationError as exc:
        logger.warning("CHART_COMMAND annotation dropped id=%s: %s", fields.get("id"), exc.errors()[:2])
        return None


def build_chat_chart_command(
    message: str,
    reply: str,
    overlay_payload: dict[str, Any],
    ai_context: dict[str, Any],
) -> dict[str, Any]:
    symbol = str(overlay_payload.get("symbol") or ai_context.get("symbol") or "")
    overlays = overlay_payload.get("overlays") or []
    price = (ai_context.get("key_levels") or {}).get("current_price")
    price = float(price) if isinstance(price, (int, float)) else None
    intents = detect_intents(message)
    explicit = _explicit_direction(message)
    direction = explicit or _bias_direction(ai_context)
    gate = build_entry_gate(ai_context)
    operations: list[dict[str, Any]] = []
    notes: list[str] = []

    if "clear" in intents:
        operations.append({"op": "clear", "scope": "ai"})

    # Timeframes the AI actually talked about rank first (grounded in its reply).
    reply_tfs = set(_TF_TOKEN.findall(reply or ""))
    quoted = [float(m.group(0)) for m in _NUMBER.finditer(reply or "")]

    def is_quoted(o: dict[str, Any]) -> bool:
        return any(abs(q - p) <= _tolerance(q) for q in quoted for p in _prices(o))

    def rank(o: dict[str, Any]) -> tuple:
        return (
            not is_quoted(o),
            o["timeframe"] not in reply_tfs and o["timeframe"] != "MTF",
            not o.get("meta", {}).get("key"),
            _distance(o, price),
        )

    def direction_ok(o: dict[str, Any], wanted: str | None) -> bool:
        return wanted is None or o["layer"] in ("trade_plan", "liquidity") or o.get("color") in (wanted, "neutral")

    # 1) Objects the question is about: live, on-direction, quoted/AI-mentioned TF first.
    layers = {layer for intent in intents for layer in _INTENT_LAYERS.get(intent, ())}
    by_intent = sorted(
        (o for o in overlays
         if o["layer"] in layers and o.get("status") in _LIVE_STATUSES and direction_ok(o, direction)),
        key=rank,
    )

    # 2) Other objects whose exact price the AI quoted. With an intent they must
    #    belong to it; an explicit buy/sell question also filters direction.
    by_quote = sorted(
        (o for o in overlays
         if is_quoted(o) and (not layers or o["layer"] in layers) and direction_ok(o, explicit)),
        key=rank,
    )

    # 3) Annotations, engine prices only.
    created: list[dict[str, Any]] = []
    focus: list[str] = []  # ids that must lead the highlight list
    plan = ai_context.get("trade_plan") or {}
    scenarios = _scenario_items(ai_context)

    if "invalidation" in intents:
        plan_scenario = next((s for s in scenarios if s.get("name") == plan.get("scenario_name")), None)
        if plan_scenario and plan_scenario.get("invalidation_reference") is None:
            notes.append(f"Engine tidak memberi level invalidasi untuk {plan_scenario.get('name')}.")
        candidates = [s for s in scenarios if s.get("invalidation_reference") is not None]
        candidates.sort(key=lambda s: (
            s is not plan_scenario,
            not any(abs(q - float(s["invalidation_reference"])) <= _tolerance(q) for q in quoted),
        ))
        for sc in candidates[:2]:
            item = _overlay(
                id=f"{symbol}:MTF:chat:invalidation:{sc.get('name')}",
                symbol=symbol, timeframe="MTF", layer="trade_plan", kind="hline",
                name=f"INVALIDATION · {sc.get('name')}", color="stop", status="waiting",
                price=sc["invalidation_reference"], source="scenario.invalidation_reference",
                created_at=overlay_payload.get("generated_at_utc"),
                meta={"scenario": sc.get("name"), "mode": sc.get("mode")},
            )
            if item:
                created.append(item)
                focus.append(item["id"])
        if not candidates:
            notes.append("Engine tidak memberi level invalidasi untuk skenario mana pun.")

    if "pullback" in intents and not gate["can_enter_now"] and price is not None and direction:
        zones = [
            o for o in overlays
            if o["layer"] in ("sr", "order_blocks", "fvg") and o.get("status") in _LIVE_STATUSES
            and o.get("color") == direction
            and any((p > price) if direction == "bearish" else (p < price) for p in _prices(o))
        ]
        zones.sort(key=lambda o: (not is_quoted(o), _distance(o, price)))
        if zones:
            zone = zones[0]
            target = (zone.get("price_low") if direction == "bearish" else zone.get("price_high")) or zone.get("price")
            item = _overlay(
                id=f"{symbol}:MTF:chat:pullback",
                symbol=symbol, timeframe="MTF", layer="trade_plan", kind="arrow",
                name="WAIT FOR CONFIRMATION", color="warning", status="waiting",
                points=[{"time": None, "price": price}, {"time": None, "price": target}],
                source=f"pullback to {zone['id']}", created_at=overlay_payload.get("generated_at_utc"),
                meta={"zone_id": zone["id"], "blockers": gate["blockers"]},
            )
            if item:
                created.append(item)
                focus.append(zone["id"])

    if "setup" in intents or "invalidation" in intents:
        focus += [o["id"] for o in overlays if o["layer"] == "trade_plan"]

    highlight = list(dict.fromkeys(
        focus + [o["id"] for o in by_quote if o in by_intent] + [o["id"] for o in by_intent] + [o["id"] for o in by_quote]
    ))[:MAX_HIGHLIGHTS]

    if created:
        operations.append({"op": "create", "overlays": created})
    if highlight:
        operations.append({"op": "highlight", "ids": highlight})

    return {
        "type": "chart_command",
        "symbol": symbol,
        "analysis_id": overlay_payload.get("analysis_id"),
        "intents": intents,
        "entry_allowed": gate["can_enter_now"],
        "blockers": gate["blockers"],
        "notes": notes,
        "operations": operations,
    }
