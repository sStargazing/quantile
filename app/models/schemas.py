"""Pydantic models for every API response."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class HomeCurrencyOut(BaseModel):
    code: str
    currency_name: str
    country: str
    display_name: str
    flag: str


class PeriodOut(BaseModel):
    key: str
    label: str
    years: int | None  # None for MAX
    # Filled in on analysis responses, where the actual window is known:
    start: date | None = None
    within: str | None = None  # "in the past 5 years" / "since Jan 2010"
    heading: str | None = None  # "Past 5 years" / "Since Jan 2010"
    average: str | None = None  # "5-year average" / "average since Jan 2010"
    average_short: str | None = None  # "5-year avg" / "avg since 2010"


class DestinationOut(BaseModel):
    id: str
    country: str
    display_name: str
    iso2: str
    currency_code: str
    currency_name: str
    flag: str
    region: str
    enabled: bool
    iso_numeric: str  # ISO 3166-1 numeric; matches the World Map geometry ids
    map_point: tuple[float, float] | None = None  # (lon, lat) marker for places too small to draw
    aliases: tuple[str, ...] = ()


class OptionsResponse(BaseModel):
    home_currencies: list[HomeCurrencyOut]
    periods: list[PeriodOut]
    default_base: str
    default_period: str


class SourceOut(BaseModel):
    name: str
    description: str
    url: str
    used_for: str


class DataQuality(BaseModel):
    fx_observations: int
    fx_first_date: date | None
    fx_latest_date: date | None
    inflation_latest_date: str | None  # latest CPI period used, e.g. "2026-06"
    cpi_frequency_home: str | None
    cpi_frequency_destination: str | None
    cpi_missing_periods: int
    complete: bool
    warnings: list[str]


class PercentileBand(BaseModel):
    key: Literal["exceptionally_weak", "weak", "typical", "strong", "exceptionally_strong"]
    label: str  # "Exceptionally strong"


class ScoreComponentOut(BaseModel):
    key: str
    label: str
    input_value: float
    points: float
    weight: float
    contribution: float


class LeaderboardEntry(BaseModel):
    rank: int | None
    status: Literal["ranked", "unavailable"]
    unavailable_reason: str | None = None
    destination: DestinationOut
    shares_currency_with: list[str]
    quantile_score: float | None = None
    fx_percentile: float | None = None
    fx_percentile_band: PercentileBand | None = None
    vs_historical_average_pct: float | None = None
    real_percentile: float | None = None
    real_percentile_band: PercentileBand | None = None
    inflation_adjustment_pts: float | None = None
    real_purchasing_power_pct: float | None = None
    current_rate: float | None = None
    current_date: date | None = None
    historical_average: float | None = None
    sparkline: list[float] = []  # the period's rates, downsampled, oldest first
    explanation: str | None = None
    score_components: list[ScoreComponentOut] = []
    data_quality: DataQuality | None = None


class LeaderboardResponse(BaseModel):
    base: HomeCurrencyOut
    period: PeriodOut
    window_start: date
    window_end: date
    generated_at: datetime
    ranked_count: int
    entries: list[LeaderboardEntry]
    warnings: list[str]
    sources: list[SourceOut]


class FxStats(BaseModel):
    pair: str
    current_rate: float
    current_date: date
    average: float
    median: float
    high: float
    high_date: date
    low: float
    low_date: date
    percentile: float
    percentile_band: PercentileBand
    share_below_pct: float  # earlier days with a strictly lower rate
    share_equal_pct: float  # earlier days with exactly the same rate (pegged currencies)
    vs_average_pct: float
    vs_median_pct: float
    one_year_change_pct: float | None
    volatility_pct: float | None
    observations: int
    first_date: date


class CountryInflation(BaseModel):
    country: str
    index_type: str
    frequency: str
    start_period: str
    end_period: str
    cumulative_pct: float
    annualised_pct: float


class InflationAnalysis(BaseModel):
    home: CountryInflation
    destination: CountryInflation
    cpi_cutoff: date
    relative_inflation_factor: float
    nominal_vs_average_pct: float
    inflation_adjustment_pts: float
    real_vs_average_pct: float
    real_percentile: float
    real_percentile_band: PercentileBand
    real_average_rate: float


class ScoreOut(BaseModel):
    quantile_score: float
    components: list[ScoreComponentOut]
    method: str


class ChartPoint(BaseModel):
    date: date
    rate: float
    real_rate: float | None = None  # historical rate restated in today's prices


class ChartData(BaseModel):
    points: list[ChartPoint]
    average: float
    real_average: float | None
    current_date: date
    current_rate: float
    total_observations: int
    downsampled: bool


class CountryResponse(BaseModel):
    status: Literal["ranked", "unavailable"]
    unavailable_reason: str | None = None
    destination: DestinationOut
    base: HomeCurrencyOut
    period: PeriodOut
    shares_currency_with: list[str]
    rank: int | None
    ranked_count: int
    headline: str | None
    explanation: str | None
    fx: FxStats | None
    inflation: InflationAnalysis | None
    score: ScoreOut | None
    chart: ChartData | None
    data_quality: DataQuality | None
    sources: list[SourceOut]
    assumptions: list[str]
    record: "RecordOut | None" = None
    generated_at: datetime


class RecordOut(BaseModel):
    """"Last time it was this good": searched over the MAX span whatever period is selected."""

    kind: Literal["today", "recent"]  # today is the high/low, or a peak/trough in the last 3 months was
    basis: Literal["nominal", "real"] = "nominal"  # "real" when only the inflation-adjusted series is notable
    statement: str  # "AUD is at its strongest against JPY since July 2024."
    direction: Literal["high", "low"]
    on: date | None = None  # "recent": the day of the peak/trough
    today_vs_extreme_pct: float | None = None
    since: date | None  # the last earlier day at least as good (high) / as bad (low); None = whole span
    span_start: date
    real_statement: str | None = None  # the inflation-adjusted equivalent, when it tells a different story
    real_direction: Literal["high", "low"] | None = None
    real_since: date | None = None


class HistoryResponse(BaseModel):
    base: str
    quote: str
    period: PeriodOut
    observations: int
    downsampled: bool
    points: list[ChartPoint]


class ConvertResponse(BaseModel):
    base: str
    to: str
    amount: float
    rate: float
    result: float
    date: date


CountryResponse.model_rebuild()
