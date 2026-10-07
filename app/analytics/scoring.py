"""The Quantile Score (0–100).

    score = 50% × real percentile  +  50% × real advantage points

* Real percentile (0–100): how unusual today's inflation-adjusted rate is
  within the period. Captures *rank* — "better than on 90% of days".
* Real advantage points (0–100): the size of today's inflation-adjusted
  advantage over the period average, mapped linearly:
      points = clamp(50 + 50 × real_vs_average% / 20, 0, 100)
  so 0% → 50 points, +10% → 75, ≥ +20% → 100, −10% → 25, ≤ −20% → 0.
  Captures *magnitude* — a percentile alone would let a currency that barely
  moves (e.g. one pegged to the US dollar) score highly for a 0.5% gain.

Both inputs are inflation-adjusted so that steady depreciation caused by high
local inflation (e.g. the Turkish lira) is not mistaken for a bargain. The
nominal percentile and nominal vs-average figures are reported alongside but
do not enter the score.

The ±20% full-scale value is a judgement: real exchange-rate deviations of
10–20% from a multi-year average are large for major currencies, so 20%
saturates the scale without making typical moves invisible. Change it (or the
weights) here; nothing else depends on the numbers.
"""

from dataclasses import dataclass

WEIGHTS = {
    "real_percentile": 0.5,
    "real_advantage": 0.5,
}
ADVANTAGE_FULL_SCALE_PCT = 20.0


@dataclass(frozen=True)
class ScoreComponent:
    key: str
    label: str
    input_value: float  # the metric fed in (percentile, or % vs average)
    points: float  # 0–100
    weight: float
    contribution: float  # points × weight


@dataclass(frozen=True)
class ScoreBreakdown:
    score: float
    components: tuple[ScoreComponent, ...]


def advantage_points(real_vs_average_pct: float) -> float:
    raw = 50.0 + 50.0 * real_vs_average_pct / ADVANTAGE_FULL_SCALE_PCT
    return max(0.0, min(100.0, raw))


def quantile_score(real_percentile: float, real_vs_average_pct: float) -> ScoreBreakdown:
    components = (
        ScoreComponent(
            "real_percentile",
            "Inflation-adjusted percentile",
            real_percentile,
            real_percentile,
            WEIGHTS["real_percentile"],
            real_percentile * WEIGHTS["real_percentile"],
        ),
        ScoreComponent(
            "real_advantage",
            "Inflation-adjusted advantage vs average",
            real_vs_average_pct,
            advantage_points(real_vs_average_pct),
            WEIGHTS["real_advantage"],
            advantage_points(real_vs_average_pct) * WEIGHTS["real_advantage"],
        ),
    )
    return ScoreBreakdown(sum(c.contribution for c in components), components)
