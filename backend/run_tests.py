import sys
import subprocess

UNIT_TEST_FILES = [
    "test_candles.py",
    "test_trade_plan.py",
    "test_ai_token_optimization.py",
    "test_trading_engine_validation.py",
    "test_ai_measurement.py",
]

LIVE_TEST_FILES = [
    "test_ai_serializer.py",
    "test_ai_reasoning.py",
    "test_trend.py",
    "test_technical.py",
    "test_stop.py",
    "test_risk.py",
    "test_confirmation.py",
    "test_trade_pipeline.py",
    "test_trade_plan_context.py",
    "test_mt5_bridge.py",
    "test_live_gemini.py",
]


def run_file(filename: str) -> bool:
    print(f"\n--- Running {filename} ---")
    res = subprocess.run([sys.executable, filename], cwd="backend")
    return res.returncode == 0


def main():
    run_live = "--live" in sys.argv
    files = UNIT_TEST_FILES + (LIVE_TEST_FILES if run_live else [])

    passed = 0
    failed = 0

    for f in files:
        ok = run_file(f)
        if ok:
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"TEST RUN SUMMARY (mode={'LIVE' if run_live else 'UNIT ONLY'})")
    print(f"PASSED: {passed}")
    print(f"FAILED: {failed}")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
