from dataclasses import dataclass, field

from app.services.analysis.context import MultiTimeframeContext


@dataclass
class PriceLevel:
    price: float
    timeframe: str
    level_type: str
    source: str


@dataclass
class LevelZone:
    price: float
    low: float
    high: float
    level_type: str
    timeframes: list[str] = field(default_factory=list)
    touches: int = 0


@dataclass
class KeyLevels:
    symbol: str
    current_price: float
    supports: list[LevelZone] = field(default_factory=list)
    resistances: list[LevelZone] = field(default_factory=list)


def _collect_levels(context: MultiTimeframeContext) -> list[PriceLevel]:
    levels = []

    for timeframe, data in context.timeframes.items():
        for swing in data.swings:
            levels.append(
                PriceLevel(
                    price=swing.price,
                    timeframe=timeframe,
                    level_type=(
                        "support"
                        if swing.type == "swing_low"
                        else "resistance"
                    ),
                    source=swing.type,
                )
            )

    return levels


def _cluster_levels(
    levels: list[PriceLevel],
    tolerance: float,
) -> list[LevelZone]:
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda level: level.price)

    clusters: list[list[PriceLevel]] = []
    current_cluster = [sorted_levels[0]]

    for level in sorted_levels[1:]:
        cluster_prices = [item.price for item in current_cluster]

        if abs(level.price - max(cluster_prices)) <= tolerance:
            current_cluster.append(level)
        else:
            clusters.append(current_cluster)
            current_cluster = [level]

    clusters.append(current_cluster)

    zones = []

    for cluster in clusters:
        prices = [level.price for level in cluster]

        # Average price becomes the representative level.
        representative_price = sum(prices) / len(prices)

        timeframes = sorted(
            set(level.timeframe for level in cluster)
        )

        zones.append(
            LevelZone(
                price=representative_price,
                low=min(prices),
                high=max(prices),
                level_type=cluster[0].level_type,
                timeframes=timeframes,
                touches=len(cluster),
            )
        )

    return zones


def build_key_levels(
    context: MultiTimeframeContext,
) -> KeyLevels:
    current_price = context.timeframes["M1"].price

    levels = _collect_levels(context)

    supports = []
    resistances = []

    for level in levels:
        if (
            level.level_type == "support"
            and level.price < current_price
        ):
            supports.append(level)

        elif (
            level.level_type == "resistance"
            and level.price > current_price
        ):
            resistances.append(level)

    # Tolerance is intentionally small.
    # EURUSD: 0.00020 ~= 2 pips
    # XAUUSD: 0.20 ~= 20 cents
    #
    # This is a first-pass clustering rule and can later become
    # symbol-aware using tick size / ATR.
    if current_price < 10:
        tolerance = 0.00020
    else:
        tolerance = 0.20

    support_zones = _cluster_levels(
        supports,
        tolerance,
    )

    resistance_zones = _cluster_levels(
        resistances,
        tolerance,
    )

    support_zones.sort(
        key=lambda zone: current_price - zone.price
    )

    resistance_zones.sort(
        key=lambda zone: zone.price - current_price
    )

    return KeyLevels(
        symbol=context.symbol,
        current_price=current_price,
        supports=support_zones,
        resistances=resistance_zones,
    )


def print_key_levels(levels: KeyLevels) -> None:
    print("\n=== KEY LEVEL ZONES ===")
    print(f"SYMBOL : {levels.symbol}")
    print(f"PRICE  : {levels.current_price}")

    print("\nSUPPORT ZONES:")

    if levels.supports:
        for zone in levels.supports[:10]:
            distance = levels.current_price - zone.price

            print(
                f"  {zone.price:.5f}"
                f" | zone={zone.low:.5f}-{zone.high:.5f}"
                f" | TF={','.join(zone.timeframes)}"
                f" | touches={zone.touches}"
                f" | distance={distance:.5f}"
            )
    else:
        print("  none")

    print("\nRESISTANCE ZONES:")

    if levels.resistances:
        for zone in levels.resistances[:10]:
            distance = zone.price - levels.current_price

            print(
                f"  {zone.price:.5f}"
                f" | zone={zone.low:.5f}-{zone.high:.5f}"
                f" | TF={','.join(zone.timeframes)}"
                f" | touches={zone.touches}"
                f" | distance={distance:.5f}"
            )
    else:
        print("  none")
