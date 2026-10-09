"""Run the setup validator on known cases and print PASS/FAIL.

Works inside the container (unlike unit tests, which are not copied there):

    docker exec ai-backend-1 python scripts/check_validator.py

It exercises the real code paths (not just constant names) and exits with
status 1 if any check fails.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai.answer_audit import audit_answer  # noqa: E402
from app.services.ai.desk import build_setups, check_view  # noqa: E402


def _ctx(price, supports, resistances, scenario):
    return {
        "key_levels": {
            "current_price": price,
            "supports": [{"price": p} for p in supports],
            "resistances": [{"price": p} for p in resistances],
        },
        "scenarios": {"current_price": price, "intraday_scenarios": [scenario]},
    }


def run_checks() -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        out.append((name, bool(ok), detail))

    # 1. the "20R" case: SL only 0.434 from price must not survive
    bear = {
        "name": "bearish_continuation", "direction": "bearish",
        "trigger_reference": 4131.238, "invalidation_reference": 4134.379,
        "atr_reference": 2.0, "trigger_confirmed": False,
    }
    s = build_setups(_ctx(4133.945, [4131.238, 4125.104], [4134.379, 4138.864], bear))[0]
    now = s["now"]
    check("tight SL replaced", now.get("raw_stop") == 4134.379 and now["stop"] != 4134.379,
          f"stop={now.get('stop')} src={now.get('stop_src')}")
    check("RR not inflated", now.get("rr", 99) < 5, f"rr={now.get('rr')}")
    check("replacement is info, not a warning",
          not any("terlalu_rapat" in f for f in now.get("flags", [])) and "stop_note" in now)

    # 2. a replacement stop must never be absurdly far; 12 ATR target rejected
    bull = {
        "name": "bullish_reversal", "direction": "bullish",
        "trigger_reference": 4194.878, "invalidation_reference": 4194.3,
        "atr_reference": 2.0, "trigger_confirmed": False,
    }
    s2 = build_setups(_ctx(4195.669, [4194.878, 4173.9], [4219.41], bull))[0]
    check("replacement stop <= 3 ATR", s2["now"]["stop_atr"] <= 3.0, f"{s2['now']['stop_atr']} ATR")
    check("unrealistic target => reject", s2["now"]["verdict"] == "reject", s2["now"]["verdict"])

    # 3. final self-check catches inconsistent numbers
    bad = {"entry": 100.0, "stop": 104.0, "target": 95.0, "risk": 4.0,
           "reward": 5.0, "rr": 9.9, "stop_atr": 2.0}
    check("check_view detects wrong RR", "rr_tidak_cocok" in check_view("bearish", bad, 2.0))
    wrong_side = {"entry": 100.0, "stop": 98.0}
    check("check_view detects stop on wrong side",
          "stop_di_sisi_salah" in check_view("bearish", wrong_side, 2.0))

    # 4. engine trigger distance vs price/ATR (user's real numbers, ATR~14)
    sc = {**bear, "trigger_reference": 4191.673, "invalidation_reference": 4211.0,
          "atr_reference": 14.0, "trigger_distance_atr": 0.02}
    ok_case = build_setups(_ctx(4191.952, [4176.9], [4211.0], sc))[0]
    check("consistent trigger distance not flagged", "checks" not in ok_case)
    sc_bad = {**sc, "trigger_distance_atr": 0.30}
    bad_case = build_setups(_ctx(4191.952, [4176.9], [4211.0], sc_bad))[0]
    check("inconsistent trigger distance flagged", "checks" in bad_case)

    # 5. answer grounding audit
    context = {"x": {"stop": 4173.348, "rr": 1.14}}
    good = audit_answer("SL 4173.35 dan RR 1.14", context)
    fake = audit_answer("SL 4173.35 dan RR 3.77", context)
    check("audit accepts rounded numbers", good["ungrounded"] == [])
    check("audit flags invented number", fake["ungrounded"] == [3.77], str(fake))

    return out


def main() -> int:
    results = run_checks()
    failed = 0
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
        failed += 0 if ok else 1
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
