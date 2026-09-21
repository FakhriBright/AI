from dataclasses import dataclass, field

from app.services.analysis.context import MultiTimeframeContext


@dataclass
class BiasGroup:
    name: str
    direction: str
    timeframes: list[str] = field(default_factory=list)
    bullish_count: int = 0
    bearish_count: int = 0
    mixed_count: int = 0


@dataclass
class MarketBias:
    symbol: str
    overall: str
    htf: BiasGroup
    intraday: BiasGroup
    entry: BiasGroup
    conflicts: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _classify_group(
    context: MultiTimeframeContext,
    name: str,
    timeframes: list[str],
) -> BiasGroup:

    bullish = 0
    bearish = 0
    mixed = 0

    for timeframe in timeframes:
        data = context.timeframes.get(timeframe)

        if data is None:
            continue

        if data.trend == "bullish":
            bullish += 1
        elif data.trend == "bearish":
            bearish += 1
        else:
            mixed += 1

    if bullish >= 2 and bullish > bearish:
        direction = "bullish"
    elif bearish >= 2 and bearish > bullish:
        direction = "bearish"
    else:
        direction = "mixed"

    return BiasGroup(
        name=name,
        direction=direction,
        timeframes=timeframes,
        bullish_count=bullish,
        bearish_count=bearish,
        mixed_count=mixed,
    )


def _detect_conflicts(
    htf: BiasGroup,
    intraday: BiasGroup,
    entry: BiasGroup,
) -> list[str]:

    conflicts = []

    if (
        htf.direction != "mixed"
        and intraday.direction != "mixed"
        and htf.direction != intraday.direction
    ):
        conflicts.append(
            f"HTF {htf.direction} conflicts with "
            f"intraday {intraday.direction}"
        )

    if (
        intraday.direction != "mixed"
        and entry.direction != "mixed"
        and intraday.direction != entry.direction
    ):
        conflicts.append(
            f"Intraday {intraday.direction} conflicts with "
            f"entry {entry.direction}"
        )

    return conflicts


def build_market_bias(
    context: MultiTimeframeContext,
) -> MarketBias:

    htf = _classify_group(
        context,
        "higher_timeframe",
        ["H4", "D1"],
    )

    intraday = _classify_group(
        context,
        "intraday",
        ["H1", "M30"],
    )

    entry = _classify_group(
        context,
        "entry",
        ["M15", "M5", "M1"],
    )

    conflicts = _detect_conflicts(
        htf,
        intraday,
        entry,
    )

    directions = [
        htf.direction,
        intraday.direction,
        entry.direction,
    ]

    bullish_groups = directions.count("bullish")
    bearish_groups = directions.count("bearish")

    if bullish_groups == 3:
        overall = "bullish"
    elif bearish_groups == 3:
        overall = "bearish"
    else:
        overall = "mixed"

    reasons = [
        f"HTF={htf.direction}",
        f"INTRADAY={intraday.direction}",
        f"ENTRY={entry.direction}",
    ]

    if conflicts:
        reasons.append("timeframe_conflict_detected")

    return MarketBias(
        symbol=context.symbol,
        overall=overall,
        htf=htf,
        intraday=intraday,
        entry=entry,
        conflicts=conflicts,
        reasons=reasons,
    )


def print_market_bias(bias: MarketBias) -> None:

    print("\n=== MARKET BIAS ===")
    print(f"SYMBOL  : {bias.symbol}")
    print(f"OVERALL : {bias.overall}")

    for group in [bias.htf, bias.intraday, bias.entry]:
        print(f"\n{group.name.upper()}")
        print(f"DIRECTION : {group.direction}")
        print(f"TIMEFRAMES: {', '.join(group.timeframes)}")
        print(f"BULLISH   : {group.bullish_count}")
        print(f"BEARISH   : {group.bearish_count}")
        print(f"MIXED     : {group.mixed_count}")

    if bias.conflicts:
        print("\nCONFLICTS:")
        for conflict in bias.conflicts:
            print(f"  - {conflict}")
    else:
        print("\nCONFLICTS: none")

    print("\nREASONS:")
    for reason in bias.reasons:
        print(f"  - {reason}")
