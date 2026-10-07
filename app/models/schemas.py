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
    years: int


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
    vs_historical_average_pct: float | None = None
    real_percentile: float | None = None
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
    generated_at: datetime


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
