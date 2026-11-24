"""Chart overlays derived from the deterministic analysis (no LLM involved).

Every overlay is computed from the same `ai_context` the AI receives, using the
engine's existing detectors, so the chart never shows something the analysis
does not contain:

- swings + HH/HL/LH/LL ........ technical/structure.py (via ai_context swings)
- BOS / CHoCH (MSS) ........... ai/desk.py structure_break
- BSL/SSL sweep ............... ai/desk.py detect_sweep
- FVG / Order Block ........... ai/desk.py detect_fvg_order_blocks
- premium / equilibrium / discount  ai/desk.py premium_discount
- support / resistance ........ analysis/levels.py (key_levels)
- trade plan / entry gate ..... trade_plan + ai/desk.py build_entry_gate

Two objects the engine did not draw before are derived here, from engine
swings only, and labelled as such in `source`:

- equal highs/lows: consecutive same-type swings within the key-level
  clustering tolerance used by analysis/levels.py (0.0002 below price 10,
  otherwise 0.20)
- trendlines: line through the last two swing lows when the later one is
  higher (bullish), or the last two swing highs when the later one is lower
  (bearish)
"""

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.schemas.chart import ChartOverlay
from app.services.ai.desk import (
    _r,
    _scenario_items,
    _short_time,
    build_entry_gate,
    detect_fvg_order_blocks,
    detect_sweep,
    premium_discount,
    structure_break,
)

logger = logging.getLogger(__name__)

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
SR_PER_SIDE = 3


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # drop NaN


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(value: Any) -> str | None:
    dt = _parse_time(value)
    return dt.isoformat() if dt else None


def _level_tolerance(price: float) -> float:
    # Same tolerance analysis/levels.py uses to cluster key levels.
    return 0.00020 if price < 10 else 0.20


def _exact(desk_value: Any, exact: float | None) -> float | None:
    """Unrounded engine price, only if it is the one desk reported.

    ai/desk.py rounds zone prices to 3 decimals for the prompt, which is too
    coarse for 5-digit FX (an EURUSD FVG collapses to zero height). The chart
    re-reads the exact value from the same candle/swing and keeps it only if
    it rounds back to desk's number, so both always describe the same zone.
    """
    if exact is None or desk_value is None or _r(exact) != desk_value:
        return None
    return exact


def _candle_index(candles: list[dict[str, Any]], short: str | None) -> int | None:
    """Map desk's truncated 'MM-DD HH:MM' time back to the exact candle."""
    if not short:
        return None
    for i in range(len(candles) - 1, -1, -1):
        if _short_time(candles[i].get("time_utc")) == short:
            return i
    return None


class _Builder:

    def __init__(self, ai_context: dict[str, Any]):
        self.ctx = ai_context
        self.symbol = str(ai_context.get("symbol") or "")
        self.generated_at = _iso(ai_context.get("generated_at_utc"))
        self.price = _num((ai_context.get("key_levels") or {}).get("current_price"))
        self.overlays: list[dict[str, Any]] = []

    def add(self, **fields: Any) -> None:
        overlay = {
            "symbol": self.symbol,
            "created_at": self.generated_at,
            "status": "active",
            "meta": {},
            **fields,
        }
        overlay["id"] = f"{self.symbol}:{overlay['timeframe']}:{overlay['id']}"
        try:
            self.overlays.append(ChartOverlay(**overlay).model_dump(exclude_none=True))
        except ValidationError as exc:
            logger.warning("CHART_OVERLAY dropped id=%s: %s", overlay.get("id"), exc.errors()[:2])

    # ---------------------------------------------------------------- structure
    def structure(self, tf: str, data: dict[str, Any]) -> None:
        swings = [s for s in data.get("swings") or [] if _num(s.get("price")) is not None]
        candles = data.get("candles") or []

        for s in swings:
            label = s.get("label") or ("SH" if s["type"] == "swing_high" else "SL")
            color = {"HH": "bullish", "HL": "bullish", "LH": "bearish", "LL": "bearish"}.get(label, "neutral")
            self.add(
                id=f"swing:{s['type']}:{s.get('time_utc')}",
                timeframe=tf, layer="structure", kind="marker",
                name=label, color=color, price=s["price"], time_start=_iso(s.get("time_utc")),
                position="above" if s["type"] == "swing_high" else "below",
                source="technical.structure.find_swings",
                meta={"swing_type": s["type"]},
            )

        if not candles:
            return
        last = candles[-1]
        verdict = structure_break(last, swings, data.get("trend"))
        kind = verdict.split(" ", 1)[0]
        if not kind.startswith(("BOS_", "CHoCH_")):
            return

        bullish = "bullish" in kind
        broken = next(
            (s for s in reversed(swings) if s["type"] == ("swing_high" if bullish else "swing_low")),
            None,
        )
        if broken is None:
            return
        is_choch = kind.startswith("CHoCH")
        self.add(
            id=f"break:{'choch' if is_choch else 'bos'}:{broken.get('time_utc')}",
            timeframe=tf, layer="structure", kind="hline",
            name=("CHoCH / MSS (candidate)" if is_choch else "BOS") + (" ↑" if bullish else " ↓"),
            color="bullish" if bullish else "bearish",
            status="candidate" if is_choch else "confirmed",
            price=broken["price"],
            time_start=_iso(broken.get("time_utc")), time_end=_iso(last.get("time_utc")),
            source="ai.desk.structure_break",
            meta={"verdict": verdict, "key": True},
        )

    # ---------------------------------------------------------------- FVG / OB
    def zones(self, tf: str, data: dict[str, Any]) -> None:
        candles = data.get("candles") or []
        found = detect_fvg_order_blocks(candles, current_price=self.price, atr=_num(data.get("atr14")))

        for zone in found["fvg"]:
            idx = _candle_index(candles, zone.get("formed_at"))
            if idx is None:
                continue
            side = zone["direction"]
            first, third = candles[idx - 2] if idx >= 2 else None, candles[idx]
            if first is None:
                continue
            if side == "bullish":
                low, high = _exact(zone["low"], _num(first.get("high"))), _exact(zone["high"], _num(third.get("low")))
            else:
                low, high = _exact(zone["low"], _num(third.get("high"))), _exact(zone["high"], _num(first.get("low")))
            if low is None or high is None:
                logger.warning("CHART_OVERLAY fvg price mismatch tf=%s formed_at=%s", tf, zone.get("formed_at"))
                continue
            self.add(
                id=f"fvg:{side}:{candles[idx].get('time_utc')}",
                timeframe=tf, layer="fvg", kind="zone",
                name=f"{side.capitalize()} FVG", color="bullish" if side == "bullish" else "bearish",
                status="active" if zone.get("fresh") else "mitigated",
                price_low=low, price_high=high,
                time_start=_iso(first.get("time_utc")),
                source="ai.desk.detect_fvg_order_blocks",
                meta={"fresh": zone.get("fresh"), "distance_atr": zone.get("distance_atr"), "key": True},
            )

        for zone in found["order_blocks"]:
            idx = _candle_index(candles, zone.get("formed_at"))
            if idx is None:
                continue
            side = zone["direction"]
            base = candles[idx]
            low, high = _exact(zone["low"], _num(base.get("low"))), _exact(zone["high"], _num(base.get("high")))
            if low is None or high is None:
                logger.warning("CHART_OVERLAY ob price mismatch tf=%s formed_at=%s", tf, zone.get("formed_at"))
                continue
            self.add(
                id=f"ob:{side}:{candles[idx].get('time_utc')}",
                timeframe=tf, layer="order_blocks", kind="zone",
                name=f"{side.capitalize()} Order Block", color="bullish" if side == "bullish" else "bearish",
                status="active" if zone.get("fresh") else "mitigated",
                price_low=low, price_high=high,
                time_start=_iso(base.get("time_utc")),
                source="ai.desk.detect_fvg_order_blocks",
                meta={"fresh": zone.get("fresh"), "distance_atr": zone.get("distance_atr"), "key": True},
            )

    # ---------------------------------------------------------------- liquidity
    def liquidity(self, tf: str, data: dict[str, Any]) -> None:
        swings = [s for s in data.get("swings") or [] if _num(s.get("price")) is not None]
        candles = data.get("candles") or []
        price = self.price

        for swing_type, name in (("swing_high", "Buy-side Liquidity (BSL)"), ("swing_low", "Sell-side Liquidity (SSL)")):
            last = next((s for s in reversed(swings) if s["type"] == swing_type), None)
            if last is None:
                continue
            resting = price is None or (last["price"] > price if swing_type == "swing_high" else last["price"] < price)
            self.add(
                id=f"liq:{'bsl' if swing_type == 'swing_high' else 'ssl'}:{last.get('time_utc')}",
                timeframe=tf, layer="liquidity", kind="hline",
                name=name, color="info", status="active" if resting else "taken",
                price=last["price"], time_start=_iso(last.get("time_utc")),
                source="ai.desk.detect_sweep (last swing high/low)",
            )

        for swing_type, name in (("swing_high", "EQH"), ("swing_low", "EQL")):
            same = [s for s in swings if s["type"] == swing_type]
            for a, b in zip(same, same[1:]):
                if abs(a["price"] - b["price"]) > _level_tolerance(a["price"]):
                    continue
                level = (a["price"] + b["price"]) / 2
                taken = price is not None and (price > max(a["price"], b["price"]) if swing_type == "swing_high"
                                               else price < min(a["price"], b["price"]))
                self.add(
                    id=f"liq:{name.lower()}:{b.get('time_utc')}",
                    timeframe=tf, layer="liquidity", kind="trendline",
                    name=f"{name} ({'buy' if swing_type == 'swing_high' else 'sell'}-side liquidity)",
                    color="info", status="taken" if taken else "active",
                    points=[{"time": _iso(a.get("time_utc")), "price": a["price"]},
                            {"time": _iso(b.get("time_utc")), "price": b["price"]}],
                    price=level,
                    source="derived: engine swings within key-level clustering tolerance",
                )

        if candles:
            sweep = detect_sweep(candles[-1], swings)
            if sweep:
                bsl = sweep.startswith("BSL")
                last = candles[-1]
                self.add(
                    id=f"sweep:{'bsl' if bsl else 'ssl'}:{last.get('time_utc')}",
                    timeframe=tf, layer="liquidity", kind="marker",
                    name="BSL sweep" if bsl else "SSL sweep",
                    color="bearish" if bsl else "bullish", status="confirmed",
                    price=last["high"] if bsl else last["low"], time_start=_iso(last.get("time_utc")),
                    position="above" if bsl else "below", shape="circle",
                    source="ai.desk.detect_sweep", meta={"verdict": sweep, "key": True},
                )

    # ---------------------------------------------------------------- trendline
    def trendlines(self, tf: str, data: dict[str, Any]) -> None:
        swings = [s for s in data.get("swings") or [] if _num(s.get("price")) is not None]
        candles = data.get("candles") or []
        last = candles[-1] if candles else None

        for swing_type, side in (("swing_low", "bullish"), ("swing_high", "bearish")):
            pts = [s for s in swings if s["type"] == swing_type][-2:]
            if len(pts) < 2:
                continue
            a, b = pts
            if (side == "bullish" and b["price"] <= a["price"]) or (side == "bearish" and b["price"] >= a["price"]):
                continue
            ta, tb = _parse_time(a.get("time_utc")), _parse_time(b.get("time_utc"))
            if not ta or not tb or tb <= ta:
                continue

            status = "active"
            tl = _parse_time(last.get("time_utc")) if last else None
            if last and tl and tl > tb:
                slope = (b["price"] - a["price"]) / (tb - ta).total_seconds()
                projected = b["price"] + slope * (tl - tb).total_seconds()
                close = _num(last.get("close"))
                if close is not None and ((side == "bullish" and close < projected) or (side == "bearish" and close > projected)):
                    status = "broken"

            self.add(
                id=f"trend:{side}:{a.get('time_utc')}",
                timeframe=tf, layer="trendline", kind="trendline",
                name=f"{side.capitalize()} trendline", color=side, status=status,
                points=[{"time": ta.isoformat(), "price": a["price"]}, {"time": tb.isoformat(), "price": b["price"]}],
                extend=True,
                source="derived: last two engine swings (HL for bullish, LH for bearish)",
            )

    # ---------------------------------------------------------------- premium / discount
    def premium_discount(self, tf: str, data: dict[str, Any]) -> None:
        swings = data.get("swings") or []
        pd = premium_discount(swings, self.price)
        if not pd or pd["state"] == "outside_range":
            return  # desk: price left the swing range, no P/D read
        # The range is the last swing high + last swing low (desk definition).
        anchors = [
            next((s for s in reversed(swings) if s.get("type") == kind and _num(s.get("price")) is not None), None)
            for kind in ("swing_high", "swing_low")
        ]
        hi = _exact(pd["range"][1], _num(anchors[0]["price"])) if anchors[0] else None
        lo = _exact(pd["range"][0], _num(anchors[1]["price"])) if anchors[1] else None
        if hi is None or lo is None:
            logger.warning("CHART_OVERLAY premium/discount range mismatch tf=%s", tf)
            return
        span = hi - lo
        times = [_parse_time(s.get("time_utc")) for s in anchors if s]
        start = min((t for t in times if t), default=None)
        common = dict(timeframe=tf, layer="premium_discount", source="ai.desk.premium_discount",
                      time_start=start.isoformat() if start else None, meta={"state": pd["state"], "pos": pd["pos"]})
        self.add(id="pd:premium", kind="zone", name="Premium", color="bearish",
                 price_low=lo + 0.55 * span, price_high=hi, **common)
        self.add(id="pd:discount", kind="zone", name="Discount", color="bullish",
                 price_low=lo, price_high=lo + 0.45 * span, **common)
        self.add(id="pd:eq", kind="hline", name="Equilibrium", color="neutral",
                 price=(lo + hi) / 2, **common)

    # ---------------------------------------------------------------- S/R
    def support_resistance(self) -> None:
        levels = self.ctx.get("key_levels") or {}
        for side, name, color in (("supports", "Support", "bullish"), ("resistances", "Resistance", "bearish")):
            for level in (levels.get(side) or [])[:SR_PER_SIDE]:
                price = _num(level.get("price"))
                if price is None:
                    continue
                tfs = [t for t in level.get("timeframes") or [] if t in TIMEFRAMES]
                tf = max(tfs, key=TIMEFRAMES.index) if tfs else "MTF"
                low, high = _num(level.get("low")), _num(level.get("high"))
                zone = low is not None and high is not None and high > low
                self.add(
                    id=f"sr:{side}:{round(price, 5)}",
                    timeframe=tf, layer="sr", kind="zone" if zone else "hline",
                    name=f"{name} ({level.get('touches') or 0}x {','.join(tfs)})".replace(" )", ")"),
                    color=color, price=price,
                    price_low=low if zone else None, price_high=high if zone else None,
                    source="analysis.levels.build_key_levels",
                    meta={"timeframes": tfs, "touches": level.get("touches")},
                )

    # ---------------------------------------------------------------- trade plan
    def trade_plan(self) -> None:
        plan = self.ctx.get("trade_plan") or {}
        gate = build_entry_gate(self.ctx)
        direction = str(plan.get("direction") or "").lower()

        entry, stop, target = (_num(plan.get(k)) for k in ("entry_price", "stop_price", "target_price"))
        if gate["can_enter_now"] and entry is not None and stop is not None:
            self.add(
                id="plan:position", timeframe="MTF", layer="trade_plan", kind="position",
                name=f"{direction.upper() or 'PLAN'} {plan.get('scenario_name') or ''}".strip(),
                color="entry", status="confirmed",
                entry=entry, stop=stop, target=target, rr=_num(plan.get("rr_ratio")),
                direction=direction or None,
                source="analysis.trade_plan.build_trade_plan",
                meta={"plan_status": plan.get("status"), "key": True},
            )
            return

        # Not executable: show WAITING with the engine's blockers, never a position.
        scenario = next(
            (s for s in _scenario_items(self.ctx) if s.get("name") == plan.get("scenario_name")),
            None,
        )
        anchor = _num((scenario or {}).get("trigger_reference")) or self.price
        if anchor is None:
            return
        self.add(
            id="plan:waiting", timeframe="MTF", layer="trade_plan", kind="label",
            name="WAITING" + (f" · {plan.get('scenario_name')}" if plan.get("scenario_name") else ""),
            color="warning", status="waiting", price=anchor,
            source="ai.desk.build_entry_gate",
            meta={"blockers": gate["blockers"], "plan_status": gate["plan_status"], "key": True},
        )

    def build(self) -> list[dict[str, Any]]:
        mtf = self.ctx.get("multi_timeframe") or {}
        for tf in TIMEFRAMES:
            data = mtf.get(tf)
            if not isinstance(data, dict):
                continue
            for step in (self.structure, self.zones, self.liquidity, self.trendlines, self.premium_discount):
                try:
                    step(tf, data)
                except Exception:
                    logger.exception("CHART_OVERLAY step=%s tf=%s failed", step.__name__, tf)
        for step in (self.support_resistance, self.trade_plan):
            try:
                step()
            except Exception:
                logger.exception("CHART_OVERLAY step=%s failed", step.__name__)
        return self.overlays


def analysis_id_for(ai_context: dict[str, Any]) -> str:
    return f"{ai_context.get('symbol')}@{_iso(ai_context.get('generated_at_utc')) or 'unknown'}"


def build_chart_overlays(ai_context: dict[str, Any]) -> dict[str, Any]:
    """`chart_overlay` payload: action=replace for the engine layer of a symbol."""
    return {
        "type": "chart_overlay",
        "symbol": ai_context.get("symbol"),
        "analysis_id": analysis_id_for(ai_context),
        "generated_at_utc": _iso(ai_context.get("generated_at_utc")),
        "action": "replace",
        "overlays": _Builder(ai_context).build(),
    }
