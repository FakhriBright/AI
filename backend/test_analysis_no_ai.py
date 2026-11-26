"""Chart-centric migration checks.

Unit part (no network): deterministic Trade Plan rules and stop placement.
Live part (real MT5 bridge data, EURUSDm + XAUUSDm): GET /analysis runs the
deterministic pipeline without creating or calling any AI provider, and the
chat endpoint still makes exactly one AI call (mock provider, no tokens used).

Run: python test_analysis_no_ai.py   (add --unit to skip the live part)
"""
import asyncio
import json
import sys
from types import SimpleNamespace

from app.api.routes import analysis as route
from app.schemas.analysis import AnalysisChatRequest
from app.services.ai.base import AIResponse
from app.services.ai.reasoning import AIReasoningService
from app.services.analysis.confirmation import ConfirmationResult
from app.services.analysis.levels import KeyLevels, LevelZone
from app.services.analysis.pipeline import _build_stop_plan
from app.services.analysis.scenario import Scenario
from app.services.analysis.trade_plan import build_trade_plan

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name} {detail}")


def zone(price: float) -> LevelZone:
    return LevelZone(price=price, low=price, high=price, level_type="level")


def scenario(direction: str, trigger=None, invalidation=None) -> Scenario:
    return Scenario(
        name=f"test_{direction}", direction=direction, status="conditional",
        trigger="t", invalidation="i",
        trigger_reference=trigger, invalidation_reference=invalidation,
    )


def confirmed(entry: float, stop=None) -> ConfirmationResult:
    return ConfirmationResult(
        scenario_name="x", confirmed=True, confirmation_type="test",
        entry_price=entry, stop_price=stop,
    )


RISK = SimpleNamespace(risk_percent=1.0, risk_amount=10.0, volume=0.1, estimated_loss=10.0)


# ---------------------------------------------------------------------------
# Unit: deterministic trade plan rules
# ---------------------------------------------------------------------------
def unit_tests() -> None:
    levels = KeyLevels(symbol="T", current_price=1.1, supports=[zone(1.0950), zone(1.0900)],
                       resistances=[zone(1.1050), zone(1.1100)])

    # 6. WAITING when the setup is not confirmed
    sc = scenario("bullish", trigger=1.1000, invalidation=1.0980)
    plan = build_trade_plan("T", sc, ConfirmationResult("x", False, "waiting_for_rejection"), levels=levels)
    check("unconfirmed -> status waiting, action WAIT, no prices",
          plan.status == "waiting" and plan.action == "WAIT"
          and plan.entry_price is None and plan.stop_price is None and plan.target_price is None)
    check("waiting plan still exposes the engine trigger / invalidation",
          plan.trigger_price == 1.1000 and plan.invalidation_price == 1.0980)

    # 7. No SL without a valid invalidation reference
    sc_noinv = scenario("bullish", trigger=1.1000, invalidation=None)
    stop, err = _build_stop_plan(confirmed(1.1010), sc_noinv)
    check("bullish confirmed without invalidation -> no stop, reason given (no ValueError)",
          stop is None and err and "invalidation" in err)
    plan = build_trade_plan("T", sc_noinv, confirmed(1.1010), stop_plan=stop, levels=levels, stop_error=err)
    check("-> plan confirmed_needs_stop, action WAIT, stop/target empty",
          plan.status == "confirmed_needs_stop" and plan.action == "WAIT"
          and plan.stop_price is None and plan.target_price is None and err in plan.warnings)
    sc_wrong = scenario("bullish", trigger=1.1000, invalidation=1.1050)  # above a bullish entry
    stop, err = _build_stop_plan(confirmed(1.1010), sc_wrong)
    check("wrong-side invalidation -> no stop (reason), no exception", stop is None and "below entry" in (err or ""))
    sc_bear = scenario("bearish", trigger=1.1000, invalidation=None)
    stop, err = _build_stop_plan(confirmed(1.0990, stop=None), sc_bear)
    check("bearish confirmed without invalidation -> no stop", stop is None and err)
    check("unconfirmed -> no stop and no error", _build_stop_plan(ConfirmationResult("x", False, "w"), sc) == (None, None))

    # 9. BUY geometry and RR
    stop, err = _build_stop_plan(confirmed(1.1010), sc)
    plan = build_trade_plan("T", sc, confirmed(1.1010), stop_plan=stop, risk_plan=RISK, levels=levels, price_digits=5)
    check("BUY: stop < entry < target, ready, action BUY",
          plan.action == "BUY" and plan.status == "ready_for_manual_review"
          and plan.stop_price < plan.entry_price < plan.target_price, json.dumps([plan.stop_price, plan.entry_price, plan.target_price]))
    check("BUY: target = nearest resistance beyond entry", plan.target_price == 1.1050)
    check("BUY: RR = (target-entry)/(entry-stop), 2 decimals",
          plan.rr_ratio == round((1.1050 - 1.1010) / (1.1010 - 1.0980), 2), str(plan.rr_ratio))

    # SELL geometry and RR
    sc_s = scenario("bearish", trigger=1.1000, invalidation=1.1030)
    stop, err = _build_stop_plan(confirmed(1.0990, stop=1.1030), sc_s)
    plan = build_trade_plan("T", sc_s, confirmed(1.0990, stop=1.1030), stop_plan=stop, risk_plan=RISK, levels=levels, price_digits=5)
    check("SELL: target < entry < stop, action SELL",
          plan.action == "SELL" and plan.target_price < plan.entry_price < plan.stop_price)
    check("SELL: target = nearest support below entry, RR from engine values",
          plan.target_price == 1.0950 and plan.rr_ratio == round((1.0990 - 1.0950) / (1.1030 - 1.0990), 2))

    # 8. No TP without a valid target
    empty = KeyLevels(symbol="T", current_price=1.1, supports=[zone(1.2)], resistances=[zone(1.0)])
    stop, err = _build_stop_plan(confirmed(1.1010), sc)
    plan = build_trade_plan("T", sc, confirmed(1.1010), stop_plan=stop, risk_plan=RISK, levels=empty)
    check("no level beyond entry -> no TP, confirmed_needs_target, action WAIT",
          plan.target_price is None and plan.rr_ratio is None
          and plan.status == "confirmed_needs_target" and plan.action == "WAIT")

    # Risk missing: levels still computed, status says what is missing
    plan = build_trade_plan("T", sc, confirmed(1.1010), stop_plan=stop, risk_plan=None, levels=levels)
    check("no account risk -> confirmed_needs_risk with entry/stop/target/RR from the engine",
          plan.status == "confirmed_needs_risk" and plan.target_price == 1.1050
          and plan.rr_ratio is not None and plan.volume is None)

    # Symbol digits
    sc_x = scenario("bullish", trigger=3575.4795, invalidation=3570.12345)
    stop, err = _build_stop_plan(confirmed(3576.8888), sc_x)
    gold = KeyLevels(symbol="X", current_price=3576.0, resistances=[zone(3590.12349)])
    plan = build_trade_plan("X", sc_x, confirmed(3576.8888), stop_plan=stop, risk_plan=RISK, levels=gold, price_digits=3)
    check("prices at broker digits (XAU 3)",
          (plan.entry_price, plan.stop_price, plan.target_price, plan.trigger_price)
          == (3576.889, 3570.123, 3590.123, round(3575.4795, 3)),
          json.dumps([plan.entry_price, plan.stop_price, plan.target_price, plan.trigger_price]))


# ---------------------------------------------------------------------------
# Live: real MT5 data, AI must not be touched by GET /analysis
# ---------------------------------------------------------------------------
class CountingProvider:
    provider = "mock"
    model = "counting"

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def analyze(self, payload):
        self.payloads.append(payload)
        return AIResponse(provider="mock", model="counting", analysis="ok", raw={"status": "ok"})


async def live_tests() -> None:
    from app.services.market_data.factory import get_market_data_provider

    ai_calls = {"factory": 0, "analyze": 0, "chat": 0}

    def exploding_factory(*args, **kwargs):
        ai_calls["factory"] += 1
        raise AssertionError("AI provider must not be created by GET /analysis")

    orig_analyze, orig_chat = AIReasoningService.analyze, AIReasoningService.chat

    async def counting_analyze(self, *a, **k):
        ai_calls["analyze"] += 1
        return await orig_analyze(self, *a, **k)

    async def counting_chat(self, *a, **k):
        ai_calls["chat"] += 1
        return await orig_chat(self, *a, **k)

    AIReasoningService.analyze = counting_analyze
    AIReasoningService.chat = counting_chat
    route.get_ai_provider_for_user = exploding_factory
    user = SimpleNamespace(risk_settings=None)
    market = get_market_data_provider()
    responses = {}

    # 1, 2, 4, 5, 10: auto-refresh style calls for both symbols, twice each
    for rnd in range(2):
        for sym in ("EURUSDm", "XAUUSDm"):
            req = SimpleNamespace(client=SimpleNamespace(host=f"no-ai-{sym}-{rnd}"))
            try:
                resp = await route.analyze_market(symbol=sym, request=req, count=300, provider=market, db=None, current_user=user)
            except Exception as exc:  # noqa: BLE001
                check(f"{sym} GET /analysis round {rnd} succeeds", False, repr(exc))
                continue
            responses[sym] = resp
            check(f"{sym} GET /analysis round {rnd} succeeds (no invalidation ValueError)", True)

    check("GET /analysis never created an AI provider", ai_calls["factory"] == 0, str(ai_calls))
    check("GET /analysis never called AI analyze/chat", ai_calls["analyze"] == 0 and ai_calls["chat"] == 0, str(ai_calls))

    for sym, resp in responses.items():
        plan = resp.trade_plan
        overlays = (resp.chart_overlays or {}).get("overlays") or []
        check(f"{sym}: ai block marked skipped", resp.ai.provider == "skipped" and resp.ai.analysis == "")
        check(f"{sym}: chart overlays built ({len(overlays)})", len(overlays) > 20)
        check(f"{sym}: overlays only for {sym}", all(o["symbol"] == sym and o["id"].startswith(f"{sym}:") for o in overlays))
        check(f"{sym}: trade plan action {plan.get('action')} / status {plan.get('status')}",
              plan.get("action") in {"BUY", "SELL", "WAIT"} and plan.get("status"))
        check(f"{sym}: plan built from the selected scenario", plan.get("scenario_name") == resp.selected_scenario["name"])
        if plan.get("action") == "WAIT":
            check(f"{sym}: WAIT plan has no full order levels",
                  not (plan.get("entry_price") and plan.get("stop_price") and plan.get("target_price")))
        if plan.get("stop_price") is not None:
            sign = 1 if plan["direction"] == "bullish" else -1
            check(f"{sym}: stop on the invalidation side of entry", sign * (plan["entry_price"] - plan["stop_price"]) > 0)
        digits = plan.get("price_digits")
        check(f"{sym}: broker digits reported ({digits})", isinstance(digits, int))
        for key in ("entry_price", "stop_price", "target_price", "trigger_price", "invalidation_price"):
            v = plan.get(key)
            if v is not None and isinstance(digits, int):
                check(f"{sym}: {key} {v} at {digits} digits", round(v, digits) == v)
        # 14. chart plan overlay mirrors the same trade plan
        pos = next((o for o in overlays if o["id"].endswith(":MTF:plan:position")), None)
        wait = next((o for o in overlays if o["id"].endswith(":MTF:plan:waiting")), None)
        if pos:
            check(f"{sym}: chart position == trade plan levels",
                  (pos.get("entry"), pos.get("stop"), pos.get("target")) == (plan.get("entry_price"), plan.get("stop_price"), plan.get("target_price")))
        else:
            check(f"{sym}: chart shows WAITING when no position is executable", wait is not None or plan.get("entry_price") is None)

    # 3, 11: chat makes exactly one AI call, with the right symbol's context
    counting = CountingProvider()
    route.get_ai_provider_for_user = lambda *a, **k: counting
    for sym in ("EURUSDm", "XAUUSDm"):
        req = SimpleNamespace(client=SimpleNamespace(host=f"chat-{sym}"))
        before = len(counting.payloads)
        try:
            out = await route.chat_analysis(
                payload=AnalysisChatRequest(symbol=sym, message="Kenapa belum ada entry? (Timeframe chart aktif: M5)", history=[]),
                request=req, symbol=sym, provider=market, db=None, current_user=user,
            )
        except Exception as exc:  # noqa: BLE001
            check(f"{sym}: chat call succeeds", False, repr(exc))
            continue
        prompt = json.dumps(counting.payloads[-1], ensure_ascii=False) if len(counting.payloads) > before else ""
        check(f"{sym}: chat -> exactly one AI provider call", len(counting.payloads) - before == 1 and out.reply == "ok")
        check(f"{sym}: chat context carries selected scenario + confirmation + trade plan",
              "selected_scenario" in prompt and "confirmation" in prompt and "trade_plan" in prompt)
        other = "XAUUSDm" if sym == "EURUSDm" else "EURUSDm"
        check(f"{sym}: chat context has no {other} data", sym in prompt and other not in prompt)
        if sym in responses:
            check(f"{sym}: chat sees the same plan action as the dashboard",
                  f'\\"action\\": \\"{responses[sym].trade_plan.get("action")}\\"' in prompt
                  or f'\\"action\\":\\"{responses[sym].trade_plan.get("action")}\\"' in prompt)


if __name__ == "__main__":
    unit_tests()
    if "--unit" not in sys.argv:
        asyncio.run(live_tests())
    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)
