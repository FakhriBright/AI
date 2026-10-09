"""The same checks as scripts/check_validator.py, run under pytest."""
import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent / "scripts" / "check_validator.py"
_spec = importlib.util.spec_from_file_location("check_validator", _path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def test_all_validator_checks_pass():
    failed = [(n, d) for n, ok, d in _mod.run_checks() if not ok]
    assert not failed, failed


def test_audit_runs_inside_chat_and_never_breaks_it(caplog):
    import asyncio
    import logging

    from app.services.ai.base import AIResponse
    from app.services.ai.reasoning import AIReasoningService

    class P:
        async def analyze(self, payload):
            return AIResponse(provider="m", model="m", analysis="SL 4999.123 RR 7.77")

    ctx = {"symbol": "XAUUSDm", "desk": {"setups": [{"ref": {"stop": 4173.348}}]}}
    with caplog.at_level(logging.WARNING):
        resp = asyncio.run(AIReasoningService(P()).chat(ctx, "setup?"))
    assert resp.analysis.startswith("SL 4999.123")          # answer untouched
    assert any("AI_GROUNDING" in r.message for r in caplog.records)
