"""Orchestration: fetch normalised data, run the analytics, shape API responses.

This is the only module that knows about both the data services and the
analytics functions. Route handlers call it; it never makes HTTP calls itself.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.analytics.fx_metrics import (
    FxSummary,
    annualised_volatility,
    change_over_days,
    share_below_and_equal,
    summarise,
)
from app.analytics.purchasing_power import RealSummary, real_summary
from app.analytics.scoring import ADVANTAGE_FULL_SCALE_PCT, WEIGHTS, ScoreBreakdown, quantile_score
from app.config.destinations import (
    Destination,
    HomeCurrency,
    Period,
    enabled_destinations,
)
from app.models import schemas
from app.models.series import DataQualityError, FxSeries, PriceIndexSeries
from app.services import narrative
from app.services.exchange_rates import PIVOT, ExchangeRateService, FxTable, years_before
from app.services.inflation import CpiDataset, InflationService
from app.settings import settings

MAX_CHART_POINTS = 600
SPARKLINE_POINTS = 60
STALE_FX_DAYS = 5  # latest observation older than this (vs. the newest in the table) is flagged
COVERAGE_TOLERANCE_DAYS = 7  # history may start this many days after the window start and still count as complete

SCORE_METHOD = (
    f"{WEIGHTS['real_percentile']:.0%} inflation-adjusted percentile + "
    f"{WEIGHTS['real_advantage']:.0%} inflation-adjusted advantage points "
    f"(0% vs average = 50 points, ±{ADVANTAGE_FULL_SCALE_PCT:.0f}% or more = 100 / 0 points)"
)


@dataclass
class DestinationResult:
    destination: Destination
    series: FxSeries | None = None
    year_series: FxSeries | None = None  # ≥ 1 year of data, for the 1-year change
    fx: FxSummary | None = None
    below_pct: float = 0.0  # share of earlier days in the window with a strictly lower rate
    equal_pct: float = 0.0  # ... with exactly the same rate (pegged currencies)
    real: RealSummary | None = None
    score: ScoreBreakdown | None = None
    home_cpi: PriceIndexSeries | None = None
    dest_cpi: PriceIndexSeries | None = None
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    rank: int | None = None

    @property
    def ranked(self) -> bool:
        return self.score is not None


@dataclass
class Computation:
    home: HomeCurrency
    period: Period
    window_start: date
    window_end: date
    generated_at: datetime
    results: list[DestinationResult]
    warnings: list[str]

    @property
    def ranked_count(self) -> int:
        return sum(1 for r in self.results if r.ranked)


def downsample_indices(n: int, max_points: int, keep: tuple[int, ...] = ()) -> list[int]:
    """Evenly spaced indices (plus first, last and any `keep`) for chart rendering only."""
    if n <= max_points:
        return list(range(n))
    step = (n - 1) / (max_points - 1)
    chosen = {round(i * step) for i in range(max_points)} | {0, n - 1} | set(keep)
    return sorted(i for i in chosen if 0 <= i < n)


class AnalysisService:
    def __init__(self, fx: ExchangeRateService, inflation: InflationService):
        self._fx = fx
        self._inflation = inflation
        self._memo: dict[tuple[str, str], tuple[float, Computation]] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    # ---- data loading -------------------------------------------------

    async def _load(self, period: Period) -> tuple[FxTable, CpiDataset]:
        today = date.today()
        fetch_from = years_before(today, max(period.years, 1)) - timedelta(days=21)
        return await asyncio.gather(self._fx.get_table(fetch_from, today), self._inflation.get_dataset())

    async def prewarm(self, longest: Period) -> None:
        await self._load(longest)

    # ---- core computation -------------------------------------------

    async def compute(self, home: HomeCurrency, period: Period) -> Computation:
        key = (home.code, period.key)
        cached = self._memo.get(key)
        if cached and cached[0] > time.time():
            return cached[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._memo.get(key)
            if cached and cached[0] > time.time():
                return cached[1]
            table, cpi = await self._load(period)
            result = self._compute(home, period, table, cpi)
            self._memo[key] = (time.time() + settings.analysis_ttl, result)
            return result

    def _compute(self, home: HomeCurrency, period: Period, table: FxTable, cpi: CpiDataset) -> Computation:
        window_end = max(s.latest_date for s in table.pivot_series.values())
        window_start = years_before(window_end, period.years)

        results = []
        for dest in enabled_destinations():
            if dest.currency_code == home.code:
                continue  # no exchange-rate story for your own currency
            results.append(self._analyse(home, dest, period, table, cpi, window_start, window_end))

        ranked = sorted(
            (r for r in results if r.ranked),
            key=lambda r: (-round(r.score.score, 6), -r.real.real_vs_mean_pct, r.destination.display_name),
        )
        for i, r in enumerate(ranked, start=1):
            r.rank = i
        unranked = sorted((r for r in results if not r.ranked), key=lambda r: r.destination.display_name)

        return Computation(
            home=home,
            period=period,
            window_start=window_start,
            window_end=window_end,
            generated_at=datetime.now(timezone.utc),
            results=ranked + unranked,
            warnings=list(dict.fromkeys(table.warnings + cpi.warnings)),
        )

    def _analyse(
        self,
        home: HomeCurrency,
        dest: Destination,
        period: Period,
        table: FxTable,
        cpi: CpiDataset,
        window_start: date,
        window_end: date,
    ) -> DestinationResult:
        r = DestinationResult(dest)
        try:
            full = table.pair(home.code, dest.currency_code)
            r.series = full.window(window_start, window_end)
            r.year_series = full.window(window_end - timedelta(days=380), window_end)
            r.fx = summarise(r.series)
            r.below_pct, r.equal_pct = share_below_and_equal(r.series.rates[:-1], r.fx.current)
        except DataQualityError as exc:
            r.reason = f"{dest.currency_code} exchange-rate history is too short to rank ({exc})."
            return r

        if (window_end - r.fx.current_date).days > STALE_FX_DAYS:
            r.warnings.append(f"{dest.currency_code} rates are only available up to {narrative.day(r.fx.current_date)}.")
        if (r.fx.first_date - window_start).days > COVERAGE_TOLERANCE_DAYS:
            r.warnings.append(
                f"{dest.currency_code} history starts on {narrative.day(r.fx.first_date)}, "
                f"after the start of the selected period ({narrative.day(window_start)})."
            )

        r.home_cpi = cpi.best_series(home.cpi_code, home.cpi_index, window_start)
        r.dest_cpi = cpi.best_series(dest.cpi_code, dest.cpi_index, window_start)
        if r.home_cpi is None or r.dest_cpi is None:
            missing = home.country if r.home_cpi is None else dest.country
            r.reason = f"No inflation data for {narrative.place(missing)}, so real purchasing power can't be calculated."
            return r
        try:
            r.real = real_summary(r.series, r.home_cpi, r.dest_cpi)
        except DataQualityError as exc:
            r.reason = f"Inflation data doesn't cover the whole period ({exc})."
            return r

        for name, series, gaps in (
            (home.country, r.home_cpi, r.real.home_cpi_gaps),
            (dest.country, r.dest_cpi, r.real.dest_cpi_gaps),
        ):
            if gaps:
                unit = "month" if series.frequency == "M" else "quarter"
                r.warnings.append(
                    f"{gaps} {unit}{'s' if gaps > 1 else ''} of inflation data missing for {narrative.place(name)}; "
                    "the previous period's price level was used instead."
                )
        r.score = quantile_score(r.real.real_percentile, r.real.real_vs_mean_pct)
        return r

    # ---- response builders --------------------------------------------

    @staticmethod
    def _quality(r: DestinationResult) -> schemas.DataQuality:
        s = r.series
        return schemas.DataQuality(
            fx_observations=len(s) if s else 0,
            fx_first_date=s.dates[0] if s else None,
            fx_latest_date=s.latest_date if s else None,
            inflation_latest_date=r.real.cpi_cutoff.strftime("%Y-%m") if r.real else None,
            cpi_frequency_home=_freq_name(r.home_cpi),
            cpi_frequency_destination=_freq_name(r.dest_cpi),
            cpi_missing_periods=(r.real.home_cpi_gaps + r.real.dest_cpi_gaps) if r.real else 0,
            complete=r.ranked and not r.warnings,
            warnings=r.warnings,
        )

    @staticmethod
    def _shares_currency(r: DestinationResult, comp: Computation) -> list[str]:
        return [
            o.destination.display_name
            for o in comp.results
            if o is not r and o.destination.currency_code == r.destination.currency_code
        ]

    def _entry(self, r: DestinationResult, comp: Computation) -> schemas.LeaderboardEntry:
        entry = schemas.LeaderboardEntry(
            rank=r.rank,
            status="ranked" if r.ranked else "unavailable",
            unavailable_reason=r.reason,
            destination=_destination_out(r.destination),
            shares_currency_with=self._shares_currency(r, comp),
            data_quality=self._quality(r),
        )
        if r.fx:
            entry.fx_percentile = r.fx.percentile
            entry.vs_historical_average_pct = r.fx.vs_mean_pct
            entry.current_rate = r.fx.current
            entry.current_date = r.fx.current_date
            entry.historical_average = r.fx.mean
            idx = downsample_indices(len(r.series), SPARKLINE_POINTS)
            entry.sparkline = [r.series.rates[i] for i in idx]
        if r.real and r.score:
            entry.quantile_score = r.score.score
            entry.real_percentile = r.real.real_percentile
            entry.inflation_adjustment_pts = r.real.inflation_adjustment_pts
            entry.real_purchasing_power_pct = r.real.real_vs_mean_pct
            entry.score_components = [schemas.ScoreComponentOut(**c.__dict__) for c in r.score.components]
            entry.explanation = narrative.explanation(
                comp.home, r.destination, comp.period, r.below_pct, r.equal_pct,
                r.real.real_vs_mean_pct, r.real.inflation_adjustment_pts,
            )
        return entry

    async def leaderboard(self, home: HomeCurrency, period: Period) -> schemas.LeaderboardResponse:
        comp = await self.compute(home, period)
        return schemas.LeaderboardResponse(
            base=_home_out(home),
            period=_period_out(period),
            window_start=comp.window_start,
            window_end=comp.window_end,
            generated_at=comp.generated_at,
            ranked_count=comp.ranked_count,
            entries=[self._entry(r, comp) for r in comp.results],
            warnings=comp.warnings,
            sources=self.sources(),
        )

    async def country(self, dest: Destination, home: HomeCurrency, period: Period) -> schemas.CountryResponse | None:
        comp = await self.compute(home, period)
        r = next((x for x in comp.results if x.destination.id == dest.id), None)
        if r is None:
            return None  # destination uses the home currency

        response = schemas.CountryResponse(
            status="ranked" if r.ranked else "unavailable",
            unavailable_reason=r.reason,
            destination=_destination_out(dest),
            base=_home_out(home),
            period=_period_out(period),
            shares_currency_with=self._shares_currency(r, comp),
            rank=r.rank,
            ranked_count=comp.ranked_count,
            headline=None,
            explanation=None,
            fx=None,
            inflation=None,
            score=None,
            chart=None,
            data_quality=self._quality(r),
            sources=self.sources(),
            assumptions=self._assumptions(r, home),
            generated_at=comp.generated_at,
        )
        if r.fx is None:
            return response

        fx = r.fx
        response.headline = narrative.headline(home, dest, period, r.below_pct, r.equal_pct)
        response.fx = schemas.FxStats(
            pair=f"{home.code}/{dest.currency_code}",
            current_rate=fx.current,
            current_date=fx.current_date,
            average=fx.mean,
            median=fx.median,
            high=fx.high,
            high_date=fx.high_date,
            low=fx.low,
            low_date=fx.low_date,
            percentile=fx.percentile,
            share_below_pct=r.below_pct,
            share_equal_pct=r.equal_pct,
            vs_average_pct=fx.vs_mean_pct,
            vs_median_pct=fx.vs_median_pct,
            one_year_change_pct=change_over_days(r.year_series, 365) if r.year_series else None,
            volatility_pct=annualised_volatility(r.series),
            observations=fx.observations,
            first_date=fx.first_date,
        )
        response.chart = self._chart(r)
        if r.real and r.score:
            real = r.real
            response.explanation = narrative.explanation(
                home, dest, period, r.below_pct, r.equal_pct, real.real_vs_mean_pct, real.inflation_adjustment_pts
            )
            response.inflation = schemas.InflationAnalysis(
                home=_country_inflation(home.country, r.home_cpi, real.home_inflation),
                destination=_country_inflation(dest.country, r.dest_cpi, real.dest_inflation),
                cpi_cutoff=real.cpi_cutoff,
                relative_inflation_factor=real.relative_inflation_factor,
                nominal_vs_average_pct=fx.vs_mean_pct,
                inflation_adjustment_pts=real.inflation_adjustment_pts,
                real_vs_average_pct=real.real_vs_mean_pct,
                real_percentile=real.real_percentile,
                real_average_rate=real.real_mean,
            )
            response.score = schemas.ScoreOut(
                quantile_score=r.score.score,
                components=[schemas.ScoreComponentOut(**c.__dict__) for c in r.score.components],
                method=SCORE_METHOD,
            )
        return response

    def _chart(self, r: DestinationResult) -> schemas.ChartData:
        s, fx = r.series, r.fx
        hi = s.rates.index(fx.high)
        lo = s.rates.index(fx.low)
        idx = downsample_indices(len(s), MAX_CHART_POINTS, keep=(hi, lo))
        real_rates = r.real.adjusted.rates if r.real else None
        return schemas.ChartData(
            points=[
                schemas.ChartPoint(date=s.dates[i], rate=s.rates[i], real_rate=real_rates[i] if real_rates else None)
                for i in idx
            ],
            average=fx.mean,
            real_average=r.real.real_mean if r.real else None,
            current_date=fx.current_date,
            current_rate=fx.current,
            total_observations=len(s),
            downsampled=len(idx) < len(s),
        )

    def _assumptions(self, r: DestinationResult, home: HomeCurrency) -> list[str]:
        dest = r.destination
        notes = [
            "Exchange rates are daily mid-market reference rates. Banks, cards and exchange bureaus add their own margins.",
            "Weekend observations are excluded because currency markets are closed.",
            f"{home.code}/{dest.currency_code} is calculated as a cross rate through {PIVOT}.",
            "Consumer price indices measure prices across the whole economy, not tourist-specific costs such as hotels or flights.",
        ]
        if r.real:
            notes.append(
                "CPI is published monthly or quarterly. Each day uses the index level of the month or quarter it falls in; "
                "no daily CPI values are interpolated."
            )
            notes.append(
                f"Both countries' CPI is cut at the latest period available for both ({r.real.cpi_cutoff:%B %Y}). "
                "Prices are assumed unchanged since then."
            )
        if dest.cpi_index == "CPI" and dest.currency_code == "EUR":
            notes.append(f"{dest.country}'s national CPI is used, so inflation figures differ between euro-area destinations.")
        if home.cpi_index == "HICP":
            notes.append("Home inflation uses the euro-area Harmonised Index of Consumer Prices (HICP).")
        return notes

    async def history(self, base: str, quote: str, period: Period, max_points: int | None) -> schemas.HistoryResponse:
        table, _ = await self._load(period)
        series = table.pair(base, quote)
        series = series.window(years_before(series.latest_date, period.years))
        idx = downsample_indices(len(series), max_points) if max_points else list(range(len(series)))
        return schemas.HistoryResponse(
            base=base,
            quote=quote,
            period=_period_out(period),
            observations=len(series),
            downsampled=len(idx) < len(series),
            points=[schemas.ChartPoint(date=series.dates[i], rate=series.rates[i]) for i in idx],
        )

    async def latest_rate(self, base: str, quote: str) -> tuple[float, date]:
        today = date.today()
        table = await self._fx.get_table(today - timedelta(days=14), today)
        series = table.pair(base, quote)
        return series.latest_rate, series.latest_date

    def sources(self) -> list[schemas.SourceOut]:
        fx, cpi = self._fx.provider, self._inflation.provider
        return [
            schemas.SourceOut(name=fx.name, description=fx.description, url=fx.url, used_for="Daily exchange rates"),
            schemas.SourceOut(name=cpi.name, description=cpi.description, url=cpi.url, used_for="Consumer price indices (inflation)"),
        ]


def _freq_name(series: PriceIndexSeries | None) -> str | None:
    if series is None:
        return None
    return {"M": "monthly", "Q": "quarterly"}[series.frequency]


def _country_inflation(country: str, series: PriceIndexSeries, infl) -> schemas.CountryInflation:
    return schemas.CountryInflation(
        country=country,
        index_type=series.index_type,
        frequency=_freq_name(series),
        start_period=infl.start_period,
        end_period=infl.end_period,
        cumulative_pct=infl.change_pct,
        annualised_pct=infl.annualised_pct,
    )


def _destination_out(d: Destination) -> schemas.DestinationOut:
    return schemas.DestinationOut(**{k: getattr(d, k) for k in schemas.DestinationOut.model_fields})


def _home_out(h: HomeCurrency) -> schemas.HomeCurrencyOut:
    return schemas.HomeCurrencyOut(**{k: getattr(h, k) for k in schemas.HomeCurrencyOut.model_fields})


def _period_out(p: Period) -> schemas.PeriodOut:
    return schemas.PeriodOut(key=p.key, label=p.label, years=p.years)
