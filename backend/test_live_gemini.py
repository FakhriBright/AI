import asyncio
from app.services.ai.factory import get_ai_provider
from app.services.ai.reasoning import AIReasoningService
from app.services.ai.metrics import metrics_collector


async def test_live_gemini():
    try:
        provider = get_ai_provider()
        print(f"Provider initialized: {provider.provider}, model: {provider.model}")
        service = AIReasoningService(provider)
        ctx = {
            "symbol": "EURUSDm",
            "market_bias": {"overall": "bullish"},
            "multi_timeframe": {"H4": {"timeframe": "H4", "price": 1.0850, "trend": "bullish"}},
            "key_levels": {"symbol": "EURUSDm", "current_price": 1.0850, "supports": [], "resistances": []},
            "scenarios": {"symbol": "EURUSDm", "scenarios": []},
            "trade_plan": {"symbol": "EURUSDm", "status": "watching"},
        }
        res = await service.analyze(ctx)
        print("Response received!")
        print("Analysis sample:", res.analysis[:100])
        print("Raw dict:", res.raw)
    except Exception as exc:
        print("Live call exception:", exc)


if __name__ == "__main__":
    asyncio.run(test_live_gemini())
