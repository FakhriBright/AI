from dataclasses import dataclass, field

from app.services.analysis.context import MultiTimeframeContext
from app.services.analysis.scenario import Scenario


@dataclass
class ConfirmationResult:
    scenario_name: str
    confirmed: bool
    confirmation_type: str
    entry_price: float | None = None
    stop_price: float | None = None
    reasons: list[str] = field(default_factory=list)


def confirm_scenario(
    context: MultiTimeframeContext,
    scenario: Scenario,
    latest_open: float,
    latest_high: float,
    latest_low: float,
    latest_close: float,
) -> ConfirmationResult:

    reasons: list[str] = []

    if scenario.direction == "bearish":
        trigger = scenario.trigger_reference

        if trigger is None:
            return ConfirmationResult(
                scenario_name=scenario.name,
                confirmed=False,
                confirmation_type="no_trigger_reference",
                reasons=["No bearish trigger reference available"],
            )

        # Bearish continuation:
        # candle must close below the trigger level.
        if latest_close < trigger:
            reasons.append(
                f"Candle close {latest_close} is below trigger {trigger}"
            )

            return ConfirmationResult(
                scenario_name=scenario.name,
                confirmed=True,
                confirmation_type="break_and_close_below",
                entry_price=latest_close,
                stop_price=scenario.invalidation_reference,
                reasons=reasons,
            )

        reasons.append(
            f"Candle close {latest_close} has not closed below trigger {trigger}"
        )

        return ConfirmationResult(
            scenario_name=scenario.name,
            confirmed=False,
            confirmation_type="waiting_for_break",
            reasons=reasons,
        )

    if scenario.direction == "bullish":
        trigger = scenario.trigger_reference

        if trigger is None:
            return ConfirmationResult(
                scenario_name=scenario.name,
                confirmed=False,
                confirmation_type="no_trigger_reference",
                reasons=["No bullish trigger reference available"],
            )

        # Bullish reversal:
        # price must touch/break support and then close back above it.
        touched_support = latest_low <= trigger
        closed_above_support = latest_close > trigger

        if touched_support and closed_above_support:
            reasons.append(
                f"Candle low {latest_low} touched/broke support {trigger}"
            )
            reasons.append(
                f"Candle close {latest_close} reclaimed support {trigger}"
            )

            return ConfirmationResult(
                scenario_name=scenario.name,
                confirmed=True,
                confirmation_type="support_rejection",
                entry_price=latest_close,
                stop_price=None,
                reasons=reasons,
            )

        if not touched_support:
            reasons.append(
                f"Candle low {latest_low} did not reach support {trigger}"
            )

        if not closed_above_support:
            reasons.append(
                f"Candle close {latest_close} did not reclaim support {trigger}"
            )

        return ConfirmationResult(
            scenario_name=scenario.name,
            confirmed=False,
            confirmation_type="waiting_for_rejection",
            reasons=reasons,
        )

    return ConfirmationResult(
        scenario_name=scenario.name,
        confirmed=False,
        confirmation_type="not_applicable",
        reasons=[
            "Range/mixed scenario does not have directional confirmation"
        ],
    )
