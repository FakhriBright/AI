"""Deterministic "trading desk" router for the AI layer.

The engine already produces closed candles, candlestick patterns, key levels,
scenarios and a trade plan. This module turns that evidence into a compact
brief and decides WHICH desk (SNR / SMC / ICT) fits each candle read, the way
a company routes a problem to the right department.

Nothing here calls an LLM and nothing here is a trade signal:
- patterns are only the ones detect_patterns() already produced;
- aliases (pin_bar + hammer, engulfing + bullish_engulfing) are collapsed
  into ONE evidence item so they can never be double counted;
- `setups` are reference levels taken from existing scenario/level fields,
  clearly labelled as NOT an engine-confirmed trade plan.
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

TF_ORDER = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")

# Relevance of a timeframe when ranking candle reads.
_TF_WEIGHT = {"H1": 5, "M15": 5, "M5": 4, "M30": 4, "H4": 3, "M1": 3, "D1": 2}
_STRENGTH_RANK = {"weak": 1, "moderate": 2, "strong": 3}
_CONVICTION_RANK = {"high": 3, "medium": 2, "low": 1}

STRUCT_TFS = ("D1", "H4", "H1", "M15", "M5")
MAX_READS = 5
MAX_SETUPS = 3

# --- setup validator thresholds (multiples of the working ATR) -------------
MIN_STOP_ATR = 0.75     # tighter than this = noise/spread will take it out
MAX_STOP_ATR = 3.0      # wider than this = risk too large for a clean setup
STOP_BUFFER_ATR = 0.25  # buffer beyond a structure level used as stop
FALLBACK_STOP_ATR = 1.0 # ATR stop when no structure level is far enough
TARGET_MIN_ATR = 1.0    # a target closer than this is not worth the trade
TARGET_MAX_ATR = 5.0    # a target further than this is unrealistic intraday
RR_SUSPICIOUS = 5.0     # RR above this almost always means a too-tight stop
ENTRY_FAR_ATR = 2.0     # pending entry further than this from price
# --- pattern relevance to the CURRENT price (multiples of working ATR) -----
REL_NEAR_ATR = 1.0
REL_OK_ATR = 2.5

# Closed candles kept per timeframe in the LLM view.
CANDLE_TAIL = {
    "chat": {"M1": 4, "M5": 5, "M15": 5, "M30": 3, "H1": 3, "H4": 2, "D1": 2},
    "analysis": {"M1": 3, "M5": 4, "M15": 4, "M30": 3, "H1": 3, "H4": 2, "D1": 2},
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Character budgets for the structured context (JSON). ~3 chars per token for
# number-heavy JSON, so 8500 chars is roughly 2.8k tokens.
def chat_context_max_chars() -> int:
    return _env_int("AI_CHAT_CONTEXT_MAX_CHARS", 8500)


def analysis_context_max_chars() -> int:
    return _env_int("AI_ANALYSIS_CONTEXT_MAX_CHARS", 7000)


def dumps(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), default=str
    )


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _r(value: Any, digits: int = 3) -> Any:
    number = _num(value)
    return round(number, digits) if number is not None else None


def _short_time(value: Any) -> str:
    text = str(value or "")
    return text[5:16].replace("T", " ") if len(text) >= 16 else text


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _direction_of(group: Any) -> str | None:
    if isinstance(group, dict):
        return group.get("direction")
    return group if isinstance(group, str) else None


# --------------------------------------------------------------------------
# candle pattern families (alias collapsing)
# --------------------------------------------------------------------------

def pattern_family(name: str) -> str:
    n = (name or "").lower()
    if "doji_star" in n:
        return "reversal_multi"
    if "dragonfly" in n or "gravestone" in n:
        return "rejection"
    if "doji" in n:
        return "indecision"
    if "morning_star" in n or "evening_star" in n or "three_inside" in n:
        return "reversal_multi"
    if "three_white" in n or "three_black" in n:
        return "continuation_multi"
    if any(k in n for k in ("engulfing", "marubozu", "belt_hold", "kicker")):
        return "displacement"
    if any(
        k in n
        for k in (
            "pin_bar",
            "hammer",
            "shooting_star",
            "tweezer",
            "piercing",
            "dark_cloud",
        )
    ):
        return "rejection"
    if "inside_bar" in n or "spinning_top" in n or "harami" in n:
        return "indecision"
    if "matching_" in n:
        return "equal_level"
    return "other"


def collapse_patterns(patterns: list[Any]) -> list[dict[str, Any]]:
    """One item per (family, direction); aliases merge into `names`."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for p in patterns or []:
        p = _as_dict(p)
        name = p.get("name")
        if not name:
            continue
        direction = p.get("direction") or "neutral"
        family = pattern_family(name)
        key = (family, direction)
        rank = _STRENGTH_RANK.get(p.get("strength"), 0)
        item = groups.get(key)

        if item is None:
            groups[key] = {
                "family": family,
                "dir": direction,
                "strength": p.get("strength"),
                "_rank": rank,
                "names": [name],
                "why": list(p.get("reasons") or [])[:2],
                "confirm": p.get("confirmation"),
            }
            continue

        if name not in item["names"]:
            item["names"].append(name)
        if rank > item["_rank"]:
            item["_rank"] = rank
            item["strength"] = p.get("strength")
            item["confirm"] = p.get("confirmation") or item["confirm"]
            item["why"] = list(p.get("reasons") or [])[:2] or item["why"]

    out = list(groups.values())
    for item in out:
        item.pop("_rank", None)
    return out


# --------------------------------------------------------------------------
# location / structure / ICT helpers (all deterministic, closed candles only)
# --------------------------------------------------------------------------

def _candle_fields(candle: Any) -> tuple[float, float, float, float] | None:
    c = _as_dict(candle)
    vals = [_num(c.get(k)) for k in ("open", "high", "low", "close")]
    if any(v is None for v in vals):
        return None
    return vals[0], vals[1], vals[2], vals[3]  # type: ignore[return-value]


def _level_zone(level: dict[str, Any]) -> tuple[float, float] | None:
    price = _num(level.get("price"))
    if price is None:
        return None
    low = _num(level.get("low"))
    high = _num(level.get("high"))
    return (low if low is not None else price, high if high is not None else price)


def locate_candle(
    candle: Any,
    atr: float | None,
    key_levels: dict[str, Any],
) -> dict[str, Any]:
    """Where the candle sits relative to key support/resistance."""
    fields = _candle_fields(candle)
    if fields is None:
        return {"at": "unknown"}
    _, high, low, close = fields
    pad = 0.25 * atr if atr else 0.0

    touched: list[tuple[int, int, str, dict[str, Any]]] = []
    for side, level_type in (("supports", "support"), ("resistances", "resistance")):
        for level in key_levels.get(side) or []:
            level = _as_dict(level)
            zone = _level_zone(level)
            if zone is None:
                continue
            if low <= zone[1] + pad and high >= zone[0] - pad:
                touched.append(
                    (
                        int(level.get("touches") or 0),
                        len(level.get("timeframes") or []),
                        level_type,
                        level,
                    )
                )

    if touched:
        touched.sort(
            key=lambda t: (abs(close - float(t[3]["price"])), -t[0], -t[1])
        )
        touches, _, level_type, level = touched[0]
        return {
            "at": level_type,
            "price": _r(level.get("price")),
            "touches": touches,
            "tfs": ",".join(level.get("timeframes") or []),
            "dist_atr": _r(abs(close - float(level["price"])) / atr, 2)
            if atr
            else None,
        }

    def nearest(side: str) -> float | None:
        prices = [
            _num(_as_dict(lv).get("price"))
            for lv in key_levels.get(side) or []
        ]
        prices = [p for p in prices if p is not None]
        if not prices:
            return None
        return min(prices, key=lambda p: abs(p - close))

    sup, res = nearest("supports"), nearest("resistances")
    out: dict[str, Any] = {"at": "mid_range"}
    if sup is not None and atr:
        out["sup_dist_atr"] = _r(abs(close - sup) / atr, 2)
    if res is not None and atr:
        out["res_dist_atr"] = _r(abs(close - res) / atr, 2)
    return out


def _last_swing(swings: list[Any], kind: str) -> dict[str, Any] | None:
    for swing in reversed(swings or []):
        swing = _as_dict(swing)
        if swing.get("type") == kind and _num(swing.get("price")) is not None:
            return swing
    return None


def detect_sweep(candle: Any, swings: list[Any]) -> str | None:
    """Wick through the latest swing but BODY closed back inside = sweep."""
    fields = _candle_fields(candle)
    if fields is None:
        return None
    _, high, low, close = fields

    sh = _last_swing(swings, "swing_high")
    if sh and high > float(sh["price"]) and close < float(sh["price"]):
        return "BSL_sweep (wick di atas swing high, body close kembali di bawah)"
    sl = _last_swing(swings, "swing_low")
    if sl and low < float(sl["price"]) and close > float(sl["price"]):
        return "SSL_sweep (wick di bawah swing low, body close kembali di atas)"
    return None


def structure_break(
    candle: Any, swings: list[Any], trend: str | None
) -> str:
    """Body close vs the last swing high/low (never a wick)."""
    fields = _candle_fields(candle)
    if fields is None:
        return "unknown"
    close = fields[3]

    sh = _last_swing(swings, "swing_high")
    sl = _last_swing(swings, "swing_low")
    if sh and close > float(sh["price"]):
        return (
            "BOS_bullish (close di atas swing high)"
            if trend == "bullish"
            else "CHoCH_bullish_candidate (close di atas swing high, melawan trend)"
        )
    if sl and close < float(sl["price"]):
        return (
            "BOS_bearish (close di bawah swing low)"
            if trend == "bearish"
            else "CHoCH_bearish_candidate (close di bawah swing low, melawan trend)"
        )
    return "di dalam range swing"


def _nth_sunday(year: int, month: int, n: int) -> datetime:
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    offset = (6 - first.weekday()) % 7  # Monday=0 ... Sunday=6
    return first + timedelta(days=offset + 7 * (n - 1))


def _ny_offset_hours(dt_utc: datetime) -> int:
    """US Eastern offset without tzdata (works on Windows)."""
    start = _nth_sunday(dt_utc.year, 3, 2).replace(hour=7)  # 2:00 EST
    end = _nth_sunday(dt_utc.year, 11, 1).replace(hour=6)  # 2:00 EDT
    return -4 if start <= dt_utc < end else -5


def killzone(generated_at: Any) -> dict[str, Any] | None:
    try:
        dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)

    ny = dt + timedelta(hours=_ny_offset_hours(dt))
    minutes = ny.hour * 60 + ny.minute
    windows = (
        ("London Open", 2 * 60, 5 * 60),
        ("NY AM", 8 * 60 + 30, 11 * 60),
        ("NY PM", 13 * 60 + 30, 16 * 60),
    )
    active = next((n for n, a, b in windows if a <= minutes < b), None)
    return {
        "ny_time": ny.strftime("%H:%M"),
        "active": active,
        "in_killzone": active is not None,
    }


def premium_discount(swings: list[Any], price: float | None) -> dict[str, Any] | None:
    sh = _last_swing(swings, "swing_high")
    sl = _last_swing(swings, "swing_low")
    if not sh or not sl or price is None:
        return None
    hi, lo = float(sh["price"]), float(sl["price"])
    if hi <= lo:
        return None
    pos = (price - lo) / (hi - lo)
    if pos > 1 or pos < 0:
        # price already left the swing range (structure broke): no P/D read
        state = "outside_range"
    else:
        state = "premium" if pos > 0.55 else "discount" if pos < 0.45 else "equilibrium"
    return {
        "range": [_r(lo), _r(hi)],
        "eq": _r((hi + lo) / 2),
        "pos": _r(pos, 2),
        "state": state,
        # discount = murah = area beli; premium = mahal = area jual
        "favors": {"discount": "buy", "premium": "sell"}.get(state, "netral"),
    }


def pattern_relevance(
    where: dict[str, Any],
    candle: Any,
    price: float | None,
    work_atr: float | None,
) -> tuple[str, float | None]:
    """Is this pattern relevant to the CURRENT price? (exists != relevant)

    near / ok / far / unknown, judged against the level the pattern sits on.
    """
    if price is None or not work_atr:
        return "unknown", None

    if where.get("at") in ("support", "resistance") and where.get("price") is not None:
        dist = abs(float(where["price"]) - price) / work_atr
    else:
        fields = _candle_fields(candle)
        if fields is None:
            return "unknown", None
        _, high, low, _ = fields
        if low - 0.5 * work_atr <= price <= high + 0.5 * work_atr:
            return "ok", 0.0
        dist = min(abs(price - high), abs(price - low)) / work_atr

    label = "near" if dist <= REL_NEAR_ATR else "ok" if dist <= REL_OK_ATR else "far"
    return label, _r(dist, 2)


_FAR_ROUTE = {
    "desk": ["SNR"],
    "play": "Pola ini terjadi jauh dari harga sekarang: konteks historis, bukan dasar entry.",
    "needs": "Abaikan untuk setup saat ini; tunggu harga mendekati level pola itu.",
}


# --------------------------------------------------------------------------
# routing playbook: candle family + location -> desk + plan
# --------------------------------------------------------------------------

def _route(read: dict[str, Any]) -> dict[str, Any]:
    family, direction = read["family"], read["dir"]
    where = read.get("where", {})
    at = where.get("at")
    sweep = read.get("sweep")
    aligned_level = (direction == "bullish" and at == "support") or (
        direction == "bearish" and at == "resistance"
    )
    counter_level = (direction == "bullish" and at == "resistance") or (
        direction == "bearish" and at == "support"
    )
    side_word = "buy" if direction == "bullish" else "sell"
    break_dir = "di atas high" if direction == "bullish" else "di bawah low"

    if family == "rejection":
        if aligned_level:
            desks = ["SNR"] + (["SMC"] if sweep else [])
            return {
                "desk": desks,
                "play": f"Rejection {direction} tepat di {at} {where.get('price')}"
                + (f" setelah {sweep.split(' ')[0]}" if sweep else "")
                + ": reaksi level yang valid, tapi bukan entry sendirian.",
                "needs": f"Candle berikutnya close {break_dir} pola (atau CHoCH {direction}) baru {side_word}.",
            }
        if counter_level:
            return {
                "desk": ["SNR"],
                "play": f"Rejection {direction} menabrak {at} {where.get('price')}: kemungkinan hanya pullback, bukan pembalikan.",
                "needs": "Tunggu break & hold melewati level itu, jangan lawan level.",
            }
        return {
            "desk": ["SMC"],
            "play": "Rejection di tengah range tanpa level pendukung: bobot rendah.",
            "needs": "Butuh sweep likuiditas atau BOS/CHoCH searah sebelum dianggap setup.",
        }

    if family == "indecision":
        if at in ("support", "resistance"):
            return {
                "desk": ["SNR"],
                "play": f"Ragu-ragu (indecision) di {at} {where.get('price')}: pasar menimbang breakout vs rejection.",
                "needs": "Jangan entry di candle ini. Tunggu close terarah: breakout body atau rejection yang jelas.",
            }
        return {
            "desk": ["SNR"],
            "play": "Indecision di tengah range: tidak ada edge.",
            "needs": "Tunggu harga mendekati level atau candle displacement.",
        }

    if family == "displacement":
        return {
            "desk": ["SMC", "ICT"],
            "play": f"Candle displacement {direction}: tanda aliran order institusi, tapi mengejar di sini berisiko.",
            "needs": "Cari retest body/OB candle ini atau retracement OTE 61.8-79% sebelum entry searah.",
        }

    if family == "reversal_multi":
        return {
            "desk": ["SMC"],
            "play": f"Pola reversal multi-candle {direction}: kandidat MSS/CHoCH.",
            "needs": "Valid hanya jika structure break terkonfirmasi (lihat structure.break) dan selaras HTF atau di level.",
        }

    if family == "continuation_multi":
        return {
            "desk": ["ICT"],
            "play": f"Momentum lanjutan {direction}: tren sedang didorong kuat.",
            "needs": "Entry di pullback (OTE/retest), bukan di candle ketiga yang sudah extended.",
        }

    if family == "equal_level":
        return {
            "desk": ["SMC", "SNR"],
            "play": "Equal high/low = kolam likuiditas.",
            "needs": "Waspada sweep dulu sebelum arah sebenarnya; tunggu reaksi setelah sweep.",
        }

    return {
        "desk": ["SNR"],
        "play": "Pola terdeteksi tapi tidak punya playbook khusus.",
        "needs": "Gunakan level dan struktur sebagai dasar keputusan.",
    }


# --------------------------------------------------------------------------
# entry gate and conditional setups
# --------------------------------------------------------------------------

_STATUS_BLOCKERS = {
    "waiting": "Belum ada trigger yang terkonfirmasi (trade plan status: waiting).",
    "confirmed_needs_stop": "Trigger terkonfirmasi tetapi stop belum valid.",
    "confirmed_needs_risk": "Trigger terkonfirmasi tetapi risk settings belum diisi.",
}


def _scenario_items(ai_context: dict[str, Any]) -> list[dict[str, Any]]:
    sc = _as_dict(ai_context.get("scenarios"))
    items: list[dict[str, Any]] = []
    if isinstance(sc.get("scenarios"), list):
        items += [dict(s) for s in sc["scenarios"] if isinstance(s, dict)]
    for key in ("intraday_scenarios", "scalp_scenarios"):
        for s in sc.get(key) or []:
            if isinstance(s, dict):
                items.append({**s, "mode": key.split("_")[0]})
    return items


def build_entry_gate(ai_context: dict[str, Any]) -> dict[str, Any]:
    plan = _as_dict(ai_context.get("trade_plan"))
    status = plan.get("status")
    can_enter = (
        status == "ready_for_manual_review"
        and plan.get("entry_price") is not None
    )

    blockers: list[str] = []
    if not can_enter:
        blockers.append(
            _STATUS_BLOCKERS.get(status, f"Trade plan belum siap (status: {status}).")
        )
        for sc in _scenario_items(ai_context):
            if not sc.get("trigger_confirmed") and sc.get("trigger_reference") is not None:
                dist = _r(sc.get("trigger_distance_atr"), 2)
                blockers.append(
                    f"[{sc.get('mode') or 'intraday'}] {sc.get('name')}: trigger {_r(sc.get('trigger_reference'))}"
                    + (f" masih {dist} ATR" if dist is not None else "")
                    + f" ({sc.get('breakout_status', 'awaiting')})"
                )
                if len(blockers) >= 3:
                    break

    conflicts = list(_as_dict(ai_context.get("market_bias")).get("conflicts") or [])
    return {
        "can_enter_now": bool(can_enter),
        "plan_status": status,
        "blockers": blockers[:3],
        "tf_conflicts": conflicts[:2],
    }


def _pattern_side(
    reads: list[dict[str, Any]] | None, direction: str
) -> tuple[list[str], list[str]]:
    """Pattern evidence that supports / opposes a setup direction."""
    pro: list[str] = []
    con: list[str] = []
    for block in reads or []:
        if block.get("rel") == "far":
            continue
        for pat in block.get("patterns", []):
            if pat.get("dir") not in ("bullish", "bearish"):
                continue
            label = f"{block.get('tf')} {pat['family']} [{'+'.join(pat['names'][:2])}]"
            (pro if pat["dir"] == direction else con).append(label)
    return pro[:3], con[:3]


def _work_atr(ai_context: dict[str, Any], sc: dict[str, Any]) -> float | None:
    """Scale used for all validator thresholds: the scenario ATR, else M15/M5."""
    atr = _num(sc.get("atr_reference"))
    if atr:
        return atr
    mtf = _as_dict(ai_context.get("multi_timeframe"))
    for tf in ("M15", "M5"):
        atr = _num(_as_dict(mtf.get(tf)).get("atr14"))
        if atr:
            return atr
    return None


# Flags that make a setup unusable as presented (not just "be careful").
_HARD_FLAGS = ("stop_terlalu_lebar", "target_terlalu_jauh", "tidak_ada_target_layak")


def _order_type(
    direction: str, entry: float, price: float | None, atr: float | None
) -> str | None:
    """buy_limit / buy_stop / sell_limit / sell_stop / market (geometry only)."""
    if price is None:
        return None
    if abs(entry - price) <= 0.1 * (atr or 0.0):
        return "market"
    if direction == "bullish":
        return "buy_limit" if entry < price else "buy_stop"
    return "sell_limit" if entry > price else "sell_stop"


def _plan_view(
    direction: str,
    entry: float,
    stop: float,
    target: float | None,
    atr: float | None,
    levels: dict[str, Any],
    price: float | None,
    check_entry_far: bool = False,
) -> dict[str, Any]:
    """Validate one entry/stop/target view and recompute RR (backend, not LLM).

    A stop that is too tight is REPLACED by a structure/ATR based stop, and
    the original is kept as raw_stop. The verdict is ok / warn / reject.
    """
    flags: list[str] = []
    bearish = direction == "bearish"
    view: dict[str, Any] = {"entry": _r(entry)}

    if (bearish and stop <= entry) or (not bearish and stop >= entry):
        view["note"] = "harga sudah melewati stop; setup tidak valid untuk entry di sini"
        view["verdict"] = "reject"
        return view

    risk = abs(stop - entry)
    src = "scenario"

    if atr:
        stop_atr = risk / atr
        if stop_atr < MIN_STOP_ATR:
            raw = stop
            far_enough = entry + MIN_STOP_ATR * atr if bearish else entry - MIN_STOP_ATR * atr
            side = "resistances" if bearish else "supports"
            pool = [_num(_as_dict(l).get("price")) for l in levels.get(side) or []]
            pool = [
                p for p in pool
                if p is not None and (p >= far_enough if bearish else p <= far_enough)
            ]
            struct_stop = None
            if pool:
                base = min(pool) if bearish else max(pool)
                struct_stop = (
                    base + STOP_BUFFER_ATR * atr if bearish else base - STOP_BUFFER_ATR * atr
                )
            if struct_stop is not None and abs(struct_stop - entry) <= MAX_STOP_ATR * atr:
                stop = struct_stop
                src = "struktur+buffer"
            else:
                stop = entry + FALLBACK_STOP_ATR * atr if bearish else entry - FALLBACK_STOP_ATR * atr
                src = "atr"
                if struct_stop is not None:
                    flags.append("level_struktur_terlalu_jauh_pakai_atr")
            risk = abs(stop - entry)
            view["raw_stop"] = _r(raw)
            flags.append(f"stop_scenario_terlalu_rapat({stop_atr:.2f}ATR)_diganti")
        final_atr = risk / atr
        if final_atr > MAX_STOP_ATR:
            flags.append(f"stop_terlalu_lebar({final_atr:.1f}ATR)")
        view["stop_atr"] = _r(final_atr, 2)
        if check_entry_far and price is not None:
            gap = abs(entry - price) / atr
            if gap > ENTRY_FAR_ATR:
                flags.append(f"entry_jauh_dari_harga({gap:.1f}ATR)")
    else:
        flags.append("atr_tidak_tersedia")

    view["stop"] = _r(stop)
    view["risk"] = _r(risk)
    view["stop_src"] = src

    if target is None:
        flags.append("tidak_ada_target_layak")
        view["verdict"] = "reject"
        view["flags"] = flags
        return view

    reward = (entry - target) if bearish else (target - entry)
    if reward <= 0:
        view["note"] = "harga sudah melewati target"
        view["verdict"] = "reject"
        view["flags"] = flags
        return view

    rr = reward / risk
    view["target"] = _r(target)
    view["reward"] = _r(reward)
    view["rr"] = _r(rr, 2)
    if atr and reward / atr < TARGET_MIN_ATR:
        flags.append(f"target_terlalu_dekat({reward / atr:.2f}ATR)")
    if atr and reward / atr > TARGET_MAX_ATR:
        flags.append(f"target_terlalu_jauh({reward / atr:.1f}ATR)")
    if rr < 1:
        flags.append("rr_di_bawah_1")
    if rr > RR_SUSPICIOUS:
        flags.append("rr_tidak_wajar_tinggi")

    hard = any(f.startswith(_HARD_FLAGS) for f in flags)
    view["verdict"] = "reject" if hard else "warn" if flags else "ok"
    if flags:
        view["flags"] = flags
    return view


def build_setups(
    ai_context: dict[str, Any],
    reads: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Conditional setups from existing scenario + key level fields only.

    Every number the LLM may quote is computed and VALIDATED here:
    - ref : entering at entry_ref (pending order at the trigger level)
    - now : entering at the current market price
    Stops that are too tight are replaced (structure/ATR based); targets that
    are too close are flagged; RR is always recomputed by the backend.
    """
    levels = _as_dict(ai_context.get("key_levels"))
    price = _num(levels.get("current_price"))
    if price is None:
        price = _num(_as_dict(ai_context.get("scenarios")).get("current_price"))
    out: list[dict[str, Any]] = []

    for sc in _scenario_items(ai_context):
        direction = sc.get("direction")
        entry = _num(sc.get("trigger_reference"))
        stop = _num(sc.get("invalidation_reference"))
        if direction not in ("bullish", "bearish") or entry is None or stop is None:
            continue
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        if direction == "bearish" and stop <= entry:
            continue
        if direction == "bullish" and stop >= entry:
            continue

        atr = _work_atr(ai_context, sc)
        # A target closer than half the risk (or one ATR) is noise: skip it.
        min_gap = max(0.5 * risk, TARGET_MIN_ATR * atr if atr else 0.0)

        target: float | None = None
        if direction == "bearish":
            pool = [_num(_as_dict(l).get("price")) for l in levels.get("supports") or []]
            pool = [p for p in pool if p is not None and p <= entry - min_gap]
            target = max(pool) if pool else None
        else:
            pool = [_num(_as_dict(l).get("price")) for l in levels.get("resistances") or []]
            pool = [p for p in pool if p is not None and p >= entry + min_gap]
            target = min(pool) if pool else None

        setup: dict[str, Any] = {
            "scenario": sc.get("name"),
            "mode": sc.get("mode") or "intraday",
            "dir": direction,
            "conviction": sc.get("conviction"),
            "confirmed": bool(sc.get("trigger_confirmed")),
            "trigger_dist_atr": _r(sc.get("trigger_distance_atr"), 2),
            "ref": _plan_view(direction, entry, stop, target, atr, levels, price, True),
        }
        order = _order_type(direction, entry, price, atr)
        if order:
            setup["ref"]["order"] = order
        if price is not None:
            setup["now"] = _plan_view(direction, price, stop, target, atr, levels, price)

        pro, con = _pattern_side(reads, direction)
        if pro:
            setup["patterns_for"] = pro
        if con:
            setup["patterns_against"] = con
        out.append(setup)

    verdict_rank = {"ok": 0, "warn": 1, "reject": 2}
    out.sort(
        key=lambda s: (
            not s["confirmed"],
            verdict_rank.get(_as_dict(s.get("now") or s["ref"]).get("verdict"), 2),
            -_CONVICTION_RANK.get(s.get("conviction"), 0),
            s["trigger_dist_atr"] if s["trigger_dist_atr"] is not None else 99,
        )
    )
    return out[:MAX_SETUPS]


# --------------------------------------------------------------------------
# the brief
# --------------------------------------------------------------------------

def build_desk_brief(ai_context: dict[str, Any]) -> dict[str, Any]:
    mtf = _as_dict(ai_context.get("multi_timeframe"))
    key_levels = _as_dict(ai_context.get("key_levels"))
    bias = _as_dict(ai_context.get("market_bias"))
    htf_dir = _direction_of(bias.get("htf"))

    # One reference price + ATR scale for the whole brief (same snapshot).
    ref_price = _num(key_levels.get("current_price"))
    if ref_price is None:
        ref_price = _num(_as_dict(mtf.get("M5")).get("price"))
    work_atr = None
    for _tf in ("M15", "M5"):
        work_atr = _num(_as_dict(mtf.get(_tf)).get("atr14"))
        if work_atr:
            break

    flat: list[dict[str, Any]] = []
    blocks: dict[str, dict[str, Any]] = {}
    no_pattern: list[str] = []

    for tf in TF_ORDER:
        data = _as_dict(mtf.get(tf))
        if not data:
            continue
        candles = data.get("candles") or []
        last = candles[-1] if candles else None
        collapsed = collapse_patterns(data.get("patterns") or [])

        if not collapsed:
            if last is not None:
                no_pattern.append(tf)
            continue

        atr = _num(data.get("atr14"))
        where = locate_candle(last, atr, key_levels)
        sweep = detect_sweep(last, data.get("swings") or [])
        fields = _candle_fields(last)
        rel, rel_dist = pattern_relevance(where, last, ref_price, work_atr or atr)

        blocks[tf] = {
            "tf": tf,
            "rel": rel,
            "rel_dist_atr": rel_dist,
            "candle": (
                [_short_time(_as_dict(last).get("time_utc")), *map(lambda v: _r(v), fields)]
                if fields
                else None
            ),
            "where": where,
            "sweep": sweep,
            "patterns": [],
        }

        for item in collapsed:
            read: dict[str, Any] = {
                "tf": tf,
                **item,
                "where": where,
                "sweep": sweep,
                "vs_htf": (
                    "n/a"
                    if item["dir"] == "neutral" or htf_dir in (None, "mixed", "neutral")
                    else "searah" if item["dir"] == htf_dir else "melawan"
                ),
            }
            read["rel"] = rel
            read["route"] = dict(_FAR_ROUTE) if rel == "far" else _route(read)
            flat.append(read)

    flat.sort(
        key=lambda r: (
            r["rel"] == "far",
            r["family"] == "other",
            -_STRENGTH_RANK.get(r.get("strength"), 0),
            -_TF_WEIGHT.get(r["tf"], 0),
        )
    )
    flat = flat[:MAX_READS]

    # Group by timeframe: candle/location/sweep are stated once per TF.
    for i, read in enumerate(flat):
        block = blocks[read["tf"]]
        entry = {
            k: read[k]
            for k in ("family", "dir", "strength", "names", "why", "vs_htf", "route")
        }
        if i == 0 and read.get("confirm"):
            entry["engine_confirmation"] = read["confirm"]
        block["patterns"].append(entry)

    reads = [
        blocks[tf]
        for tf in dict.fromkeys(r["tf"] for r in flat)
    ]

    structure: dict[str, Any] = {}
    for tf in STRUCT_TFS:
        data = _as_dict(mtf.get(tf))
        if not data:
            continue
        candles = data.get("candles") or []
        swings = data.get("swings") or []
        structure[tf] = {
            "trend": data.get("trend"),
            "structure": data.get("structure"),
            "break": structure_break(
                candles[-1] if candles else None, swings, data.get("trend")
            ),
            "swings": [
                f"{_as_dict(s).get('label') or _as_dict(s).get('type')} {_r(_as_dict(s).get('price'), 2)}"
                for s in swings[-3:]
            ],
        }

    price = _num(key_levels.get("current_price"))
    if price is None:
        price = _num(_as_dict(mtf.get("M5")).get("price"))

    ict: dict[str, Any] = {}
    kz = killzone(ai_context.get("generated_at_utc"))
    if kz:
        ict["killzone"] = kz
    pd: dict[str, Any] = {}
    for tf in ("H1", "M15"):
        item = premium_discount(_as_dict(mtf.get(tf)).get("swings") or [], price)
        if item:
            pd[tf] = item
    if pd:
        ict["premium_discount"] = pd

    desks: list[str] = []
    for read in flat:
        if read["rel"] == "far":
            continue
        for desk in read["route"]["desk"]:
            if desk not in desks:
                desks.append(desk)
    if "SNR" not in desks:
        desks.append("SNR")
    if (kz or {}).get("active") and "ICT" not in desks:
        desks.append("ICT")

    brief: dict[str, Any] = {
        "price": _r(price),
        "snapshot": {
            "time_utc": ai_context.get("generated_at_utc"),
            "price": _r(ref_price),
            "atr_m15": _r(work_atr),
        },
        "candle_format": "[time_utc,open,high,low,close] closed candle terakhir",
        "reads": reads,
        "no_pattern_tfs": no_pattern,
        "structure": structure,
        "ict": ict,
        "entry_gate": build_entry_gate(ai_context),
        "setups": build_setups(ai_context, reads),
        "setups_note": (
            "Referensi dari level/scenario engine, BUKAN trade plan terkonfirmasi. "
            "ref = entry di level trigger (pending); now = entry di harga sekarang. "
            "Semua angka sudah divalidasi backend (stop/target/RR)."
        ),
        "unavailable": ["FVG", "order block eksplisit", "fundamental/news"],
        "desks": desks,
    }
    return brief


# --------------------------------------------------------------------------
# slim views for the LLM
# --------------------------------------------------------------------------

def _pattern_labels(patterns: list[Any]) -> list[str]:
    return [
        f"{c['dir']} {c['family']} {c['strength']} [{'+'.join(c['names'])}]"
        for c in collapse_patterns(patterns)
    ]


def slim_multi_timeframe(
    mtf: dict[str, Any], mode: str = "chat"
) -> dict[str, Any]:
    tails = CANDLE_TAIL.get(mode, CANDLE_TAIL["chat"])
    out: dict[str, Any] = {}

    for tf, data in _as_dict(mtf).items():
        data = _as_dict(data)
        item: dict[str, Any] = {
            "trend": data.get("trend"),
            "structure": data.get("structure"),
            "ema": data.get("ema_alignment"),
            "rsi": _r(data.get("rsi14"), 1),
            "macd_hist": _r(data.get("macd_hist"), 3),
            "atr": _r(data.get("atr14"), 3),
        }
        candles = data.get("candles") or []
        n = tails.get(tf, 3)
        item["candles"] = [
            [_short_time(_as_dict(c).get("time_utc")), *(_r(_as_dict(c).get(k)) for k in ("open", "high", "low", "close"))]
            for c in candles[-n:]
        ]
        labels = _pattern_labels(data.get("patterns") or [])
        if labels:
            item["patterns"] = labels
        out[tf] = {k: v for k, v in item.items() if v is not None}

    return out


def slim_levels(levels: dict[str, Any], per_side: int = 3) -> dict[str, Any]:
    levels = _as_dict(levels)
    price = _num(levels.get("current_price"))

    def side(items: list[Any]) -> list[dict[str, Any]]:
        rows = [_as_dict(i) for i in items or []]
        if price is not None:
            rows.sort(key=lambda l: abs((_num(l.get("price")) or price) - price))
        return [
            {
                "price": _r(l.get("price")),
                "zone": [_r(l.get("low")), _r(l.get("high"))],
                "touches": l.get("touches"),
                "tfs": ",".join(l.get("timeframes") or []),
            }
            for l in rows[:per_side]
        ]

    return {
        "current_price": _r(price),
        "supports": side(levels.get("supports")),
        "resistances": side(levels.get("resistances")),
    }


def slim_scenarios(ai_context: dict[str, Any], rationale: int = 2) -> dict[str, Any]:
    keep = (
        "name",
        "mode",
        "direction",
        "status",
        "breakout_status",
        "conviction",
        "trigger_reference",
        "invalidation_reference",
        "trigger_distance_atr",
        "near_trigger",
        "trigger_confirmed",
    )
    items = []
    for sc in _scenario_items(ai_context):
        row = {k: sc.get(k) for k in keep if sc.get(k) is not None}
        for k in ("trigger_reference", "invalidation_reference"):
            if k in row:
                row[k] = _r(row[k])
        if "trigger_distance_atr" in row:
            row["trigger_distance_atr"] = _r(row["trigger_distance_atr"], 2)
        if rationale and sc.get("rationale"):
            row["rationale"] = list(sc["rationale"])[:rationale]
        items.append(row)
    return {
        "current_price": _r(_as_dict(ai_context.get("scenarios")).get("current_price")),
        "scenarios": items,
    }


def slim_bias(bias: Any) -> Any:
    bias = _as_dict(bias)
    if not bias:
        return bias
    return {
        "overall": bias.get("overall"),
        "htf": _direction_of(bias.get("htf")),
        "intraday": _direction_of(bias.get("intraday")),
        "entry": _direction_of(bias.get("entry")),
        "conflicts": list(bias.get("conflicts") or [])[:2],
    }


_PLAN_KEYS = (
    "scenario_name",
    "direction",
    "status",
    "entry_price",
    "stop_price",
    "target_price",
    "rr_ratio",
    "risk_percent",
    "risk_amount",
    "volume",
    "estimated_loss",
    "confirmation_type",
    "stop_method",
)


def slim_trade_plan(plan: Any) -> dict[str, Any]:
    plan = _as_dict(plan)
    out = {k: plan[k] for k in _PLAN_KEYS if plan.get(k) is not None}
    for key in ("reasons", "warnings", "conflicts"):
        if plan.get(key):
            out[key] = list(plan[key])[:3]
    if out.get("reasons") or out.get("warnings"):
        out["live_check_note"] = (
            "reasons/warnings can quote the LIVE still-forming M1 candle "
            "(trigger check); closed-candle evidence is only in desk/candles."
        )
    return out


# --------------------------------------------------------------------------
# budget guard
# --------------------------------------------------------------------------

def context_size(ctx: dict[str, Any]) -> int:
    return len(dumps(ctx))


def _cut_candles(ctx: dict[str, Any], n: int) -> None:
    for item in _as_dict(ctx.get("multi_timeframe")).values():
        if isinstance(item, dict) and isinstance(item.get("candles"), list):
            item["candles"] = item["candles"][-n:]


def _drop_rationale(ctx: dict[str, Any]) -> None:
    for sc in _as_dict(ctx.get("scenarios")).get("scenarios") or []:
        if isinstance(sc, dict):
            sc.pop("rationale", None)


def _cut_levels(ctx: dict[str, Any], n: int) -> None:
    kl = _as_dict(ctx.get("key_levels"))
    for side in ("supports", "resistances"):
        if isinstance(kl.get(side), list):
            kl[side] = kl[side][:n]


def _cut_desk(ctx: dict[str, Any]) -> None:
    desk = _as_dict(ctx.get("desk"))
    if isinstance(desk.get("reads"), list):
        desk["reads"] = desk["reads"][:3]
        for block in desk["reads"]:
            for pat in block.get("patterns", []):
                pat.pop("engine_confirmation", None)
                pat.pop("why", None)
    if isinstance(desk.get("setups"), list):
        desk["setups"] = desk["setups"][:2]


def _slim_mtf_indicators(ctx: dict[str, Any]) -> None:
    for item in _as_dict(ctx.get("multi_timeframe")).values():
        if isinstance(item, dict):
            for key in ("atr", "patterns"):
                item.pop(key, None)


def _drop_mtf(ctx: dict[str, Any]) -> None:
    ctx.pop("multi_timeframe", None)


def _drop_structure(ctx: dict[str, Any]) -> None:
    _as_dict(ctx.get("desk")).pop("structure", None)


# Lowest-value data goes first; candle evidence is trimmed last.
_SHRINK_STEPS = (
    _drop_rationale,
    lambda c: _cut_levels(c, 2),
    _slim_mtf_indicators,
    lambda c: _cut_candles(c, 4),
    lambda c: _cut_candles(c, 3),
    _cut_desk,
    lambda c: _cut_candles(c, 2),
    _drop_structure,
    _drop_mtf,
)


def shrink_to_budget(ctx: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Return a copy of ctx trimmed (lowest-value data first) to max_chars."""
    if context_size(ctx) <= max_chars:
        return ctx

    work = copy.deepcopy(ctx)
    for step in _SHRINK_STEPS:
        step(work)
        if context_size(work) <= max_chars:
            break
    return work


def build_analysis_llm_context(ai_context: dict[str, Any]) -> dict[str, Any]:
    """Compact context for the full analysis prompt."""
    ctx: dict[str, Any] = {
        "symbol": ai_context.get("symbol"),
        "generated_at_utc": ai_context.get("generated_at_utc"),
        "market_bias": slim_bias(ai_context.get("market_bias")),
        "trade_plan": slim_trade_plan(ai_context.get("trade_plan")),
        "desk": build_desk_brief(ai_context),
        "multi_timeframe": slim_multi_timeframe(
            ai_context.get("multi_timeframe") or {}, "analysis"
        ),
        "key_levels": slim_levels(ai_context.get("key_levels") or {}, 4),
        "scenarios": slim_scenarios(ai_context),
    }
    return ctx
