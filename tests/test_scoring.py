import pytest

from app.analytics.fx_metrics import summarise
from app.analytics.purchasing_power import real_summary
from app.analytics.scoring import advantage_points, quantile_score
from tests.helpers import cpi, fx


@pytest.mark.parametrize(
    "pct, points",
    [(0, 50), (10, 75), (20, 100), (35, 100), (-10, 25), (-20, 0), (-50, 0)],
)
def test_advantage_points_mapping(pct, points):
    assert advantage_points(pct) == pytest.approx(points)


def test_score_is_weighted_sum_of_components():
    b = quantile_score(real_percentile=90.0, real_vs_average_pct=10.0)
    assert b.score == pytest.approx(0.5 * 90 + 0.5 * 75)
    assert sum(c.weight for c in b.components) == pytest.approx(1.0)
    assert b.score == pytest.approx(sum(c.contribution for c in b.components))


def test_score_is_bounded():
    assert quantile_score(100.0, 500.0).score == pytest.approx(100.0)
    assert quantile_score(0.0, -500.0).score == pytest.approx(0.0)


def test_score_increases_with_each_component():
    assert quantile_score(80, 5).score > quantile_score(70, 5).score
    assert quantile_score(80, 6).score > quantile_score(80, 5).score


def test_stronger_purchasing_power_scores_higher_end_to_end():
    history = [100.0 + (i % 7) for i in range(40)]
    flat = cpi("X", {f"2024-M{m:02d}": 100.0 for m in range(1, 13)})

    def score(today):
        series = fx(history + [today])
        r = real_summary(series, flat, flat)
        return quantile_score(r.real_percentile, r.real_vs_mean_pct).score

    assert score(115.0) > score(103.0) > score(90.0)
