from dataclasses import dataclass
import logging
from typing import Any

logger = logging.getLogger("ai_metrics")


@dataclass
class FeatureMetrics:
    call_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tokens_saved: int = 0
    token_type: str = "ACTUAL"  # ACTUAL or ESTIMATED


class AIMetricsCollector:
    def __init__(self):
        self.features: dict[str, FeatureMetrics] = {
            "Full Analysis": FeatureMetrics(),
            "AI Analyst Chat": FeatureMetrics(),
            "Auto Refresh": FeatureMetrics(),
        }

    def reset(self):
        for f in self.features.values():
            f.call_count = 0
            f.cache_hits = 0
            f.cache_misses = 0
            f.prompt_tokens = 0
            f.completion_tokens = 0
            f.total_tokens = 0
            f.tokens_saved = 0
            f.token_type = "ACTUAL"

    def record_call(
        self,
        feature: str,
        provider: str,
        model: str,
        cache_status: str,
        prompt_tokens: int,
        completion_tokens: int,
        token_type: str = "ACTUAL",
        tokens_saved: int = 0,
    ):
        if feature not in self.features:
            self.features[feature] = FeatureMetrics()

        fm = self.features[feature]
        fm.token_type = token_type

        if cache_status == "HIT":
            fm.cache_hits += 1
            fm.tokens_saved += tokens_saved
            logger.info(
                f"AI_CACHE feature={feature} provider={provider} model={model} "
                f"cache=HIT tokens_saved={tokens_saved} type={token_type}"
            )
        else:
            fm.call_count += 1
            fm.cache_misses += 1
            fm.prompt_tokens += prompt_tokens
            fm.completion_tokens += completion_tokens
            fm.total_tokens += (prompt_tokens + completion_tokens)
            logger.info(
                f"AI_CALL feature={feature} provider={provider} model={model} "
                f"cache=MISS input_tokens={prompt_tokens} output_tokens={completion_tokens} "
                f"total_tokens={prompt_tokens + completion_tokens} type={token_type}"
            )

    def summary(self) -> dict[str, Any]:
        return {
            name: {
                "calls": fm.call_count,
                "input": fm.prompt_tokens,
                "output": fm.completion_tokens,
                "total": fm.total_tokens,
                "cache_hits": fm.cache_hits,
                "cache_misses": fm.cache_misses,
                "tokens_saved": fm.tokens_saved,
                "type": fm.token_type,
            }
            for name, fm in self.features.items()
        }


metrics_collector = AIMetricsCollector()
