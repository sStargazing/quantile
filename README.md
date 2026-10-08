# Quantile

**Where does my money currently go further than it normally does?**

**Live:** https://quantile-w5si.onrender.com · [World Map](https://quantile-w5si.onrender.com/map)

Quantile ranks popular travel destinations by how favourable today's exchange
rate is for your home currency *compared with that currency pair's own
history*, after adjusting for inflation at home and in the destination. It is
deliberately interpretable: every score can be traced back to a handful of
published numbers, and the app shows all of them.

Quantile describes the past; it is not a forecast or financial advice.

---

## Running it

Requires Python 3.11+ (developed on 3.13).

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # optional; defaults work without it
.venv/bin/uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Interactive API docs are at `/docs`.

The first request downloads up to 10 years of daily exchange rates (about 20
seconds); the server starts this in the background at startup. After that, data
is served from the on-disk cache in `.cache/quantile/` and pages load instantly.

### Deployment

The live site at https://quantile-w5si.onrender.com runs on [Render](https://render.com) as a
Python web service connected to this GitHub repository:

| Setting | Value |
|---|---|
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

Pushing to `main` triggers a new deploy (Render's Auto-Deploy). No environment
variables or keys are required. The data cache lives on the instance's disk, so
after a deploy or restart the first request re-downloads exchange-rate history
(about 20 seconds); the server starts that download in the background at
startup. To keep the cache across deploys, attach a Render persistent disk and
set `CACHE_DIR` to a path on it.

### Tests

```bash
.venv/bin/python -m pytest
```

The suite needs no network: analytics are tested against hand-calculated
examples, and the full user flow runs through the FastAPI app with both external
APIs replaced by synthetic data.

---

## Environment variables

See `.env.example`. All are optional.

| Variable | Default | Purpose |
|---|---|---|
| `FX_API_BASE_URL` | `https://api.frankfurter.dev/v2` | Exchange-rate provider |
| `CPI_API_BASE_URL` | `https://api.imf.org/external/sdmx/2.1` | CPI provider |
| `EXCHANGE_RATE_API_KEY`, `INFLATION_API_KEY` | – | Reserved for keyed providers (the current ones need none). Server-side only. |
| `CACHE_DIR` | `.cache/quantile` | File cache location |
| `FX_CURRENT_TTL`, `FX_RECENT_TTL`, `FX_HISTORY_TTL`, `CPI_TTL`, `ANALYSIS_TTL` | 1 h, 7 d, 90 d, 7 d, 10 min | Cache lifetimes |
| `PREWARM_ON_STARTUP` | `true` | Fetch history in the background at startup |

`.env` is git-ignored. No key ever reaches the browser: the frontend only talks
to Quantile's own API.

---

## Data providers

| Data | Provider | Notes |
|---|---|---|
| Daily exchange rates | [Frankfurter v2](https://frankfurter.dev) | Reference rates blended from central-bank publications (ECB, Federal Reserve, RBA, …). Bulk date ranges, no key. |
| Consumer price indices | [IMF CPI dataset (IMF.STA:CPI)](https://data.imf.org/en/datasets/IMF.STA:CPI) | National all-items CPI, monthly and quarterly; euro-area HICP (`G163`) for EUR as a home currency. No key. |

---

## Architecture

```text
Frankfurter / IMF APIs
        ↓
app/providers/      HTTP + parsing → normalised types (FxSeries, PriceIndexSeries)
        ↓
app/services/       caching, chunking, cross rates, CPI selection    (exchange_rates.py, inflation.py, cache.py)
        ↓
app/analytics/      pure functions, no I/O                            (fx_metrics, inflation, purchasing_power, scoring)
        ↓
app/services/analysis.py   orchestration → Pydantic responses; narrative.py builds sentences from metrics
        ↓
app/api/            FastAPI routes (validation only)
        ↓
templates/ + static/   HTML, CSS, vanilla JS, dependency-free SVG chart
```

```text
app/
  main.py                 app, lifespan (HTTP client, services, prewarm), page routes
  settings.py             environment configuration
  config/destinations.py  destinations, home currencies, periods  ← edit lists here
  models/series.py        FxSeries / PriceIndexSeries, pair normalisation, cross rates
  models/schemas.py       API response models
  providers/              frankfurter.py, imf.py
  services/               cache.py, exchange_rates.py, inflation.py, analysis.py, narrative.py
  analytics/              fx_metrics.py, inflation.py, purchasing_power.py, scoring.py
  api/                    currencies.py, leaderboard.py, countries.py
templates/                base.html (shared header), leaderboard.html, map.html, country.html, converter.html
static/                   css/quantile.css, js/common.js, leaderboard.js, map.js, country.js, chart.js
static/vendor/            d3-array, d3-geo, topojson-client, world-atlas countries-110m.json
tests/
```

### API

| Route | Returns |
|---|---|
| `GET /api/options` | Home currencies, periods, defaults (for the selectors) |
| `GET /api/currencies` | Home currencies |
| `GET /api/destinations` | Destination configuration |
| `GET /api/leaderboard?base=AUD&period=5y` (period: `1y`, `3y`, `5y`, `10y`, `max`) | Ranked destinations with all metrics, score components, explanations and data quality |
| `GET /api/country/{slug or ISO2}?base=AUD&period=5y` | Full analysis for one destination: headline, statistics, inflation breakdown, score breakdown, chart series, sources, assumptions |
| `GET /api/history/{AUD-JPY}?period=5y&max_points=500` | Raw daily history for any configured pair |
| `GET /api/convert?base=AUD&to=JPY&amount=100` | Conversion at the latest rate (the original calculator) |

Pages: `/` (Leaderboard), `/map` (World Map), `/country/{slug}?base=…&period=…`, and `/converter` (the
original calculator, not linked from the header).

### World Map

`/map` shades each destination by the same Quantile Score as the Leaderboard. It
reads `GET /api/leaderboard`, so the two pages always show identical scores for
the same home currency and period, and the server reuses its cached computation.
There is no separate map endpoint or scoring code.

* **Geometry:** [world-atlas](https://github.com/topojson/world-atlas) 110m
  countries (Natural Earth, public domain), drawn with `d3-geo` (Equal Earth
  projection) and `topojson-client`. All three are vendored in
  `static/vendor/`; no map service or key is involved.
* **Matching:** countries are matched to shapes by ISO 3166-1 numeric code
  (`iso_numeric` in `app/config/destinations.py`), never by name. Singapore and
  Hong Kong are too small to draw at world scale, so they get a `map_point`
  marker. A test checks that every destination has a shape or a marker.
* **Colour:** one continuous blue scale, from light (score 0) to dark (score
  100), reversed on dark backgrounds. Countries without data are neutral grey;
  destinations that use your home currency are a darker grey.
* **Interaction:** hover (or keyboard focus) shows the score, FX percentile,
  vs-average and real purchasing power. Clicking opens the country page with the
  current selection. On touch screens, the first tap shows the numbers and a
  second tap (or "View") opens the page.

### Configuration

Destinations, home currencies and periods live in
`app/config/destinations.py`. Each destination has `id`, `country`,
`display_name`, `iso2`, `currency_code`, `currency_name`, `flag`, `region`,
`cpi_code` (IMF area code), `cpi_index` and `enabled`. To add one, add a row
with a currency Frankfurter supports and a CPI series the IMF publishes; nothing
else changes. Destinations that share a currency (France, Italy, Spain, Greece)
are listed separately: their exchange-rate analysis is identical, but each uses
its national CPI, so scores differ slightly. The UI says so. A destination
that uses the selected home currency is left out.

Taiwan was considered but is excluded: the IMF CPI dataset has no Taiwan series.

---

## Methodology

Notation: for home currency **B** and destination currency **Q**, `R_t` is the
number of units of Q bought by 1 unit of B on day *t*. Higher `R` is always
better for the traveller. All pairs are normalised to this direction internally
(`normalise_pair`, `cross_rate` in `app/models/series.py`), whichever way a
provider quotes them.

### 1. Exchange-rate data

* All currencies are fetched once against USD and every pair is derived as a
  cross rate: `R(B→Q) = R(USD→Q) / R(USD→B)`, using only dates present in both
  series. Checked against Frankfurter's direct quotes: agreement within 0.01%,
  which is rounding in the published rates.
* **Weekends are dropped.** Currency markets are closed, but a few central
  banks publish weekend rates. Keeping them would make "a day" mean different
  things for different currencies.
* Holidays and other gaps are left as gaps. Nothing is forward-filled or zeroed.
* **Window:** the latest observation date `T` (today, normally) and the same
  calendar date *N* years earlier. "Today's rate" `R_today` is the latest
  observation.
* **MAX** is the longest window every destination can be compared over: it
  starts at the latest first-available CPI period across all configured areas.
  Inflation data, not exchange rates, is the limit: every currency has daily
  rates from 1999, but Egypt, the Philippines and Thailand have CPI only from
  January 2010, so MAX currently runs from 1 Jan 2010. All destinations share
  this one window so rankings stay comparable, and it is the same for every home
  currency. An area whose CPI starts less than 10 years back is left out of the
  calculation, so a newly added short-history destination shows as "not ranked"
  for MAX instead of shrinking it below 10Y (`AnalysisService.max_window_start`).

### 2. Nominal metrics (`analytics/fx_metrics.py`)

| Metric | Definition |
|---|---|
| FX percentile | `100 × (#{R_t < R_today} + ½ × #{R_t = R_today}) / N` over the window (today included) |
| Historical average | arithmetic mean of `R_t` |
| Historical median | median of `R_t` (reported because FX distributions can be skewed) |
| vs average | `(R_today / mean − 1) × 100` |
| vs median | `(R_today / median − 1) × 100` |
| High / low | max / min with their dates |
| 1-year change | vs the last observation on or before `T − 365 days` |
| Volatility | std. dev. of daily log returns × √260, as % |

**Percentile bands.** Every percentile also gets a plain-English label
(`percentile_band`), shown next to the number across the app:

| Percentile | Label |
|---|---|
| below 10 | Exceptionally weak |
| 10 – 25 | Weak |
| 25 – 75 | Typical |
| 75 – 90 | Strong |
| 90 and above | Exceptionally strong |

"Strong" means your home currency buys more than usual. Labels are green
(strong), grey (typical) or red (weak); the colour always comes with the text.

**Ties count as half (mid-rank), a deliberate deviation from a plain
"≤ today" count.** With "≤", a pegged currency (USD → AED, whose rate never
moves) would sit at the 100th percentile. With mid-rank it sits at the 50th.
For floating currencies the two definitions differ by at most one observation.
The headline sentence uses the strictly-below share, rounded down, so it never
overstates ("1 AUD buys more JPY today than on 87% of days…"). When most days
share today's exact rate, it says so instead.

### "Last time it was this good" (country pages)

Each country page can show one sentence putting today's rate in longer context
(`record_context` and `recent_extreme` in `analytics/fx_metrics.py`). It is always
searched over the MAX span, so it doesn't change when you switch period:

* **Today is a high or low.** *"AUD is at its strongest against JPY since July
  2024."* `since` is the most recent earlier day that was at least as good (or
  as bad). This is shown only if that day is at least 60 days ago; if no earlier
  day qualifies, the sentence says "in Quantile's records (since Jan 2010)".
* **Otherwise, a recent peak or trough.** If the highest or lowest day of the
  last 3 months was the best or worst in at least half a year: *"On 1 Sep 2026,
  AUD reached its strongest against THB since July 2024. Today's rate is 1.4%
  below that peak."*
* **Inflation.** The same search runs on the inflation-adjusted series. When it
  tells a different story it is shown too (e.g. the lira is nominally at a
  record against USD, but after inflation it's only the most since Dec 2025).
* **Nothing notable** (a mid-range or pegged rate): no sentence is shown.

The date is also marked on the chart when it falls inside the selected period.

### 3. Inflation adjustment (`analytics/inflation.py`, `analytics/purchasing_power.py`)

A currency can look "cheap" simply because local prices rose. Türkiye is the
clear example: the lira bought 70% more per AUD than its 5-year average, but
Turkish prices rose even faster. Quantile therefore restates every historical
rate in today's prices:

```text
R_adj(t) = R_t × (P_dest(now) / P_dest(t)) ÷ (P_home(now) / P_home(t))
```

`R_adj(t)` is how many units of Q you would need today to match the real buying
power that 1 unit of B had on day *t*. Comparing `R_today` with `R_adj(t)` is the
same as comparing the real exchange rate `R × P_home / P_dest` today against
day *t*.

Then, mirroring the nominal metrics:

```text
Real purchasing power (real vs average) = (R_today / mean(R_adj) − 1) × 100
Inflation-adjusted percentile           = mid-rank percentile of R_today within R_adj
Inflation adjustment (percentage points) = real vs average − nominal vs average
```

The adjustment is given in percentage points, so the breakdown on the detail
page adds up exactly: nominal + adjustment = real.

Also reported, for context:

```text
Cumulative inflation     = P(latest) / P(period containing the window start) − 1   (each country)
Relative inflation factor = (1 + destination inflation) / (1 + home inflation)
```

The adjustment compares today with the *average* of the whole period, so it is
not equal to the cumulative inflation gap. The detail page explains this.

**Monthly CPI vs daily FX:**

* No daily CPI values are created or interpolated. Each day takes the index
  level of the month (or quarter) it falls in.
* Monthly CPI is used when it covers the whole window. Otherwise quarterly CPI
  is used. Australia has a full monthly CPI only from 2024, so periods longer
  than about 2 years use its quarterly index; New Zealand only publishes
  quarterly.
* **Common cutoff.** Home and destination CPI are both cut at the end of the
  latest period available for *both*, so neither side counts extra months of
  inflation. Days after the cutoff use the cutoff price level (prices assumed
  unchanged since the latest release).
* A missing CPI period inside the window (e.g. US October 2025, never published
  because of the government shutdown) keeps the previous period's level. It is
  reported as a data-quality warning.
* If CPI doesn't reach back to the start of the window, the destination is shown
  as *unavailable* with the reason, rather than being ranked on partial data.

### 4. Quantile Score (`analytics/scoring.py`)

```text
Quantile Score = 0.5 × inflation-adjusted percentile
               + 0.5 × advantage points

advantage points = clamp(50 + 50 × real_vs_average% / 20, 0, 100)
                   (0% → 50, +10% → 75, ≥ +20% → 100, −10% → 25, ≤ −20% → 0)
```

Why these two components:

* **Percentile** measures *rarity*: how unusual today is within the period.
* **Advantage points** measure *size*. A percentile alone would let a currency
  that barely moves score highly for a trivial 0.5% gain; this is real for USD
  pegs such as HKD and AED.
* **Both are inflation-adjusted**, so depreciation caused by high inflation is
  not mistaken for a bargain. The nominal percentile and nominal vs-average are
  shown alongside the score but don't enter it.
* **±20% full scale** is a judgement: real deviations of 10–20% from a
  multi-year average are large for major currencies, so 20% saturates the scale
  without hiding typical moves.
* **Equal weights:** neither rarity nor size is obviously more important, so
  neither is favoured.
* **Not included:** momentum and volatility. They describe where a rate might
  go, not how good it is today, and would make the score harder to explain.

Ranking: score descending, ties broken by real vs average, then name. The
calculation is deterministic: the same data and configuration always give the
same ranking.

Weights and the full-scale value are constants in `scoring.py`; changing them
changes nothing else. The API returns every component (`input_value`, `points`,
`weight`, `contribution`) next to the final score.

### 5. Data quality

Each leaderboard entry and detail response carries `data_quality`:
observations, first/latest FX date, latest common CPI month, CPI frequencies,
missing CPI periods, warnings, and `complete`. `complete` is false if FX
history starts more than 7 days into the window, the latest rate is more than
5 days old, any CPI period is missing, or cached data had to be served because a
refresh failed.

---

## Caching and performance

* **FX:** fetched in calendar-year chunks, concurrently. Completed years are
  cached for 90 days, earlier months of the current year for 7 days, and the
  current month for 1 hour.
* **CPI:** the whole dataset (all areas, monthly and quarterly) is fetched in
  one IMF request and cached for 7 days.
* **Computed rankings:** held in memory for 10 minutes per (home currency,
  period).
* **Scale:** a full leaderboard uses at most ~11 cached FX chunks and 1 CPI
  dataset; computing it takes under 0.1 s.
* **Failed refreshes:** if a refresh fails and an expired copy exists, that copy
  is served and flagged as stale. If nothing is cached and the provider is down,
  the API returns a readable 503.
* **Backend:** `services/cache.py` stores JSON files behind a small
  `get`/`set`/`fetch` interface, so it can later be backed by Redis or a
  database.

---

## Data limitations

* **Mid-market rates.** Reference rates are mid-market. Cards, banks and
  exchange bureaus add margins of typically 1–5%.
* **CPI isn't tourist prices.** CPI measures whole-economy consumer prices, not
  hotels, flights or restaurants in tourist areas.
* **CPI lags.** CPI is published monthly or quarterly with a delay of about 1–3
  months; the UAE series currently ends in December 2025.
* **History, not forecasts.** A high score means unusual *relative to the
  period*, not cheap in absolute terms, and says nothing about where rates will
  go.
* **Short or managed histories.** Currencies that were devalued or re-pegged
  during the window (e.g. EGP in 2023–24) have histories that mix regimes; the
  inflation adjustment absorbs much, but not all, of that.

---

## Other files

`quantile.py` and `terminal_calculator.py` are the original command-line
experiments and are not used by the web app.
