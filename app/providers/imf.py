"""IMF Consumer Price Index provider (dataset IMF.STA:CPI, SDMX 2.1 API).

The IMF compiles national CPIs (and Eurostat HICPs) into one consistent
dataset with monthly and quarterly frequencies, covering almost every country
Quantile ranks. No API key is required.
"""

import calendar
import re
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from app.models.series import PriceIndexSeries, PricePeriod
from app.providers.base import ProviderError

SOURCE = "IMF inflation (CPI) service"
_PERIOD_RE = re.compile(r"^(\d{4})-(M(\d{2})|Q([1-4]))$")


def parse_period(label: str) -> tuple[date, date]:
    """'2025-M03' → (2025-03-01, 2025-03-31); '2025-Q1' → (2025-01-01, 2025-03-31)."""
    m = _PERIOD_RE.match(label)
    if not m:
        raise ValueError(f"unsupported period {label!r}")
    year = int(m.group(1))
    if m.group(3):
        first_month = last_month = int(m.group(3))
    else:
        first_month = (int(m.group(4)) - 1) * 3 + 1
        last_month = first_month + 2
    return date(year, first_month, 1), date(year, last_month, calendar.monthrange(year, last_month)[1])


def parse_cpi_xml(content: bytes) -> dict[tuple[str, str, str], PriceIndexSeries]:
    """Parse an SDMX StructureSpecificData message into series keyed by (code, index_type, frequency)."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ProviderError(f"IMF returned malformed XML: {exc}", SOURCE) from exc

    result: dict[tuple[str, str, str], PriceIndexSeries] = {}
    for series in root.iter():
        if not series.tag.endswith("Series"):
            continue
        attrs = series.attrib
        code, index_type, freq = attrs.get("COUNTRY"), attrs.get("INDEX_TYPE"), attrs.get("FREQUENCY")
        if not (code and index_type and freq in ("M", "Q")):
            continue
        periods = []
        for obs in series:
            if not obs.tag.endswith("Obs"):
                continue
            raw = obs.attrib.get("OBS_VALUE")
            label = obs.attrib.get("TIME_PERIOD", "")
            try:
                value = float(raw) if raw not in (None, "", "NaN") else None
                start, end = parse_period(label)
            except ValueError:
                continue
            if value is None or value <= 0:
                continue  # missing observation: leave the gap, never substitute zero
            periods.append(PricePeriod(label, start, end, value))
        periods.sort(key=lambda p: p.start)
        result[(code, index_type, freq)] = PriceIndexSeries(code, index_type, freq, tuple(periods))
    return result


class ImfCpiProvider:
    name = "IMF Consumer Price Index (IMF.STA:CPI)"
    description = "National consumer price indices compiled by the International Monetary Fund (HICP for the euro area)"
    url = "https://data.imf.org/en/datasets/IMF.STA:CPI"

    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def fetch(self, codes: list[str], index_types: list[str], start_year: int) -> dict[tuple[str, str, str], PriceIndexSeries]:
        """Headline (all-items) index series, monthly and quarterly, for every requested area."""
        key = f"{'+'.join(sorted(set(codes)))}.{'+'.join(sorted(set(index_types)))}._T.IX.M+Q"
        url = f"{self._base_url}/data/IMF.STA,CPI/{key}"
        try:
            response = await self._client.get(url, params={"startPeriod": str(start_year)})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"IMF CPI request failed: {exc}", SOURCE) from exc
        return parse_cpi_xml(response.content)
