"""Chart overlays derived from the deterministic analysis (no LLM involved).

Every overlay is a drawing of an engine result; the chart never detects
anything itself:

- swings + HH/HL/LH/LL, BOS / CHoCH, FVG, order blocks, BSL/SSL pools,
  EQH/EQL, liquidity sweeps, premium/discount ... technical/smc.py, computed
  per timeframe from that timeframe's CLOSED candles (`ai_context["smc"]`,
  attached by analysis/pipeline.py). Rules are documented in smc.py.
- trendlines ........ last two confirmed swing lows (rising) / highs (falling)
- support / resistance ... analysis/levels.py (key_levels)
- trade plan / entry gate ... trade_plan + ai/desk.py build_entry_gate

Each overlay carries a stable id (symbol:timeframe:type:anchor time), its
source timeframe, exact prices, start/end times and the engine state in meta.
Unsupported concepts (IFVG, BPR, trend channels, ...) are never emitted.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.schemas.chart import ChartOverlay
from app.services.ai.desk import _scenario_items, build_entry_gate
from app.services.technical.smc import analyze as smc_analyze

logger = logging.getLogger(__name__)

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
SR_PER_SIDE = 3
SMC_SOURCE = "technical.smc"


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


# Engine zone state -> overlay lifecycle status (partial fill stays live).
ZONE_STATUS = {"fresh": "active", "partial": "active", "filled": "mitigated",
               "mitigated": "mitigated", "invalidated": "invalidated"}


class _Builder:

    def __init__(self, ai_context: dict[str, Any]):
        self.ctx = ai_context
        self.symbol = str(ai_context.get("symbol") or "")
        self.generated_at = _iso(ai_context.get("generated_at_utc"))
        self.price = _num((ai_context.get("key_levels") or {}).get("current_price"))
        self.overlays: list[dict[str, Any]] = []
        self._smc: dict[str, dict[str, Any]] = dict(ai_context.get("smc") or {})

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

    def smc(self, tf: str, data: dict[str, Any]) -> dict[str, Any]:
        """The engine's SMC read for this timeframe (pipeline). Contexts built
        without it (older callers, fixtures) get the same detector run on the
        closed candles they carry."""
        if tf not in self._smc:
            self._smc[tf] = smc_analyze(data.get("candles") or [], tf, current_price=self.price)
        return self._smc[tf]

    def _distance_atr(self, low: float, high: float, atr: float | None) -> float | None:
        if self.price is None or not atr:
            return None
        return round(max(low - self.price, self.price - high, 0) / atr, 2)

    # ---------------------------------------------------------------- structure
    def structure(self, tf: str, data: dict[str, Any]) -> None:
        smc = self.smc(tf, data)
        for s in smc["swings"]:
            label = s.get("label") or ("SH" if s["type"] == "swing_high" else "SL")
            color = {"HH": "bullish", "HL": "bullish", "LH": "bearish", "LL": "bearish"}.get(label, "neutral")
            self.add(
                id=f"swing:{s['type']}:{s['time']}",
                timeframe=tf, layer="structure", kind="marker",
                name=label, color=color, status="confirmed", price=s["price"], time_start=_iso(s["time"]),
                position="above" if s["type"] == "swing_high" else "below",
                source=f"{SMC_SOURCE} swings (fractal {smc['config']['swing_lookback']})",
                meta={"swing_type": s["type"], "confirmed_time": _iso(s.get("confirmed_time"))},
            )

        for ev in smc["events"]:
            bullish = ev["direction"] == "bullish"
            choch = ev["kind"] == "CHoCH"
            self.add(
                id=f"break:{'choch' if choch else 'bos'}:{ev['swing_time']}",
                timeframe=tf, layer="structure", kind="hline",
                name=f"{ev['kind']} {'↑' if bullish else '↓'}",
                color="bullish" if bullish else "bearish", status="confirmed",
                price=ev["level"], time_start=_iso(ev["swing_time"]), time_end=_iso(ev["break_time"]),
                source=f"{SMC_SOURCE} structure (close beyond swing)",
                meta={
                    "key": True, "break_time": _iso(ev["break_time"]), "break_close": ev["break_close"],
                    "swing_label": ev.get("swing_label"), "prior_trend": ev.get("prior_trend"),
                    "initial": ev.get("initial"),
                    "verdict": f"{ev['kind']} {ev['direction']}: close {ev['break_close']} beyond "
                               f"{ev.get('swing_label') or 'swing'} {ev['level']}",
                },
            )

    # ---------------------------------------------------------------- FVG / OB
    def zones(self, tf: str, data: dict[str, Any]) -> None:
        smc = self.smc(tf, data)
        atr = smc.get("atr")
        for z in smc["fvgs"]:
            side = z["direction"]
            self.add(
                id=f"fvg:{side}:{z['formed_time']}",
                timeframe=tf, layer="fvg", kind="zone",
                name=f"{side.capitalize()} FVG", color=side, status=ZONE_STATUS[z["state"]],
                price_low=z["low"], price_high=z["high"],
                time_start=_iso(z["start_time"]), time_end=_iso(z.get("end_time")),
                source=f"{SMC_SOURCE} fvg (3-candle gap)",
                meta={
                    "key": True, "state": z["state"], "fill_pct": z.get("fill_pct"),
                    "fresh": z["state"] == "fresh", "formed_time": _iso(z["formed_time"]),
                    "displacement_time": _iso(z["displacement_time"]),
                    "distance_atr": self._distance_atr(z["low"], z["high"], atr),
                },
            )
        for z in smc["order_blocks"]:
            side = z["direction"]
            self.add(
                id=f"ob:{side}:{z['ob_time']}",
                timeframe=tf, layer="order_blocks", kind="zone",
                name=f"{side.capitalize()} Order Block", color=side, status=ZONE_STATUS[z["state"]],
                price_low=z["low"], price_high=z["high"],
                time_start=_iso(z["ob_time"]), time_end=_iso(z.get("end_time")),
                source=f"{SMC_SOURCE} order block ({z['break_kind']}-validated)",
                meta={
                    "key": True, "state": z["state"], "fresh": z["state"] == "fresh",
                    "definition": z["definition"], "break_kind": z["break_kind"],
                    "break_time": _iso(z["break_time"]), "broken_level": z["broken_level"],
                    "displacement_time": _iso(z["displacement_time"]),
                    "distance_atr": self._distance_atr(z["low"], z["high"], atr),
                },
            )

    # ---------------------------------------------------------------- liquidity
    def liquidity(self, tf: str, data: dict[str, Any]) -> None:
        liq = self.smc(tf, data)["liquidity"]
        for pool in liq["pools"]:
            bsl = pool["side"] == "BSL"
            self.add(
                id=f"liq:{'bsl' if bsl else 'ssl'}:{pool['swing_time']}",
                timeframe=tf, layer="liquidity", kind="hline",
                name="Buy-side Liquidity (BSL)" if bsl else "Sell-side Liquidity (SSL)",
                color="info", status="active" if pool["state"] == "resting" else "taken",
                price=pool["price"], time_start=_iso(pool["swing_time"]),
                source=f"{SMC_SOURCE} liquidity (unswept swing {'high' if bsl else 'low'})",
                meta={"swing_label": pool.get("swing_label"), "state": pool["state"]},
            )
        for eq in liq["equal_levels"]:
            high_side = eq["kind"] == "EQH"
            self.add(
                id=f"liq:{eq['kind'].lower()}:{eq['points'][1]['time']}",
                timeframe=tf, layer="liquidity", kind="trendline",
                name=f"{eq['kind']} ({'buy' if high_side else 'sell'}-side liquidity)",
                color="info", status="active" if eq["state"] == "resting" else "taken",
                points=[{"time": _iso(pt["time"]), "price": pt["price"]} for pt in eq["points"]],
                price=eq["price"],
                source=f"{SMC_SOURCE} equal swings (ATR tolerance)",
                meta={"tolerance": eq["tolerance"], "state": eq["state"], "taken_time": _iso(eq.get("taken_time"))},
            )
        for sw in liq["sweeps"]:
            bsl = sw["side"] == "BSL"
            self.add(
                id=f"sweep:{'bsl' if bsl else 'ssl'}:{sw['sweep_time']}",
                timeframe=tf, layer="liquidity", kind="marker",
                name="BSL sweep" if bsl else "SSL sweep",
                color="bearish" if bsl else "bullish", status="confirmed",
                price=sw["extreme"], time_start=_iso(sw["sweep_time"]),
                position="above" if bsl else "below", shape="circle",
                source=f"{SMC_SOURCE} sweep (wick beyond, close back inside)",
                meta={
                    "key": True, "level": sw["level"], "swing_time": _iso(sw["swing_time"]),
                    "levels": sw.get("levels") or [sw["level"]], "close": sw["close"],
                    "verdict": f"{sw['side']} sweep of {sw.get('swing_label') or 'swing'} {sw['level']}: "
                               f"wick {sw['extreme']}, closed back at {sw['close']}",
                },
            )

    # ---------------------------------------------------------------- trendline
    def trendlines(self, tf: str, data: dict[str, Any]) -> None:
        smc = self.smc(tf, data)
        swings = smc["swings"]
        candles = data.get("candles") or []
        last_time = candles[-1].get("time_utc") if candles else smc.get("last_closed_time")
        last_close = _num(candles[-1].get("close")) if candles else None

        for swing_type, side in (("swing_low", "bullish"), ("swing_high", "bearish")):
            pts = [s for s in swings if s["type"] == swing_type][-2:]
            if len(pts) < 2:
                continue
            a, b = pts
            if (side == "bullish" and b["price"] <= a["price"]) or (side == "bearish" and b["price"] >= a["price"]):
                continue
            ta, tb = _parse_time(a["time"]), _parse_time(b["time"])
            if not ta or not tb or tb <= ta:
                continue

            status = "active"
            tl = _parse_time(last_time)
            if tl and tl > tb and last_close is not None:
                slope = (b["price"] - a["price"]) / (tb - ta).total_seconds()
                projected = b["price"] + slope * (tl - tb).total_seconds()
                if (side == "bullish" and last_close < projected) or (side == "bearish" and last_close > projected):
                    status = "broken"

            self.add(
                id=f"trend:{side}:{a['time']}",
                timeframe=tf, layer="trendline", kind="trendline",
                name=f"{side.capitalize()} trendline", color=side, status=status,
                points=[{"time": ta.isoformat(), "price": a["price"]}, {"time": tb.isoformat(), "price": b["price"]}],
                extend=True,
                source="derived: last two confirmed swings (HL for bullish, LH for bearish)",
            )

    # ---------------------------------------------------------------- premium / discount
    def premium_discount(self, tf: str, data: dict[str, Any]) -> None:
        dr = self.smc(tf, data).get("dealing_range")
        if not dr or dr.get("state") in (None, "outside_range"):
            return  # price left the dealing range: no premium/discount read
        times = [t for t in (_parse_time(dr["high_time"]), _parse_time(dr["low_time"])) if t]
        start = min(times) if times else None
        common = dict(
            timeframe=tf, layer="premium_discount", source=f"{SMC_SOURCE} dealing range (last swing high/low)",
            time_start=start.isoformat() if start else None,
            meta={
                "state": dr["state"], "pos": round(dr["position"], 2),
                "range_high": dr["high"], "range_high_time": _iso(dr["high_time"]),
                "range_low": dr["low"], "range_low_time": _iso(dr["low_time"]),
            },
        )
        self.add(id="pd:premium", kind="zone", name="Premium", color="bearish",
                 price_low=dr["premium_from"], price_high=dr["high"], **common)
        self.add(id="pd:discount", kind="zone", name="Discount", color="bullish",
                 price_low=dr["low"], price_high=dr["discount_to"], **common)
        self.add(id="pd:eq", kind="hline", name="Equilibrium", color="neutral",
                 price=dr["equilibrium"], **common)

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
