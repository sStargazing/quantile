import re

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import analysis_service, resolve_base, resolve_period
from app.config.destinations import DEFAULT_BASE, DEFAULT_PERIOD, all_currency_codes, get_destination
from app.models import schemas
from app.services.analysis import AnalysisService

router = APIRouter(prefix="/api", tags=["countries"])


@router.get("/country/{country_code}", response_model=schemas.CountryResponse)
async def country(
    country_code: str,
    base: str = DEFAULT_BASE,
    period: str = DEFAULT_PERIOD,
    service: AnalysisService = Depends(analysis_service),
):
    """Full analysis for one destination. `country_code` is a slug ("japan") or ISO code ("JP")."""
    dest = get_destination(country_code)
    if dest is None:
        raise HTTPException(status_code=404, detail=f"Unknown destination '{country_code}'.")
    home = resolve_base(base)
    result = await service.country(dest, home, resolve_period(period))
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"{dest.display_name} uses {dest.currency_code}, the same currency as your home currency.",
        )
    return result


@router.get("/history/{currency_pair}", response_model=schemas.HistoryResponse)
async def history(
    currency_pair: str,
    period: str = DEFAULT_PERIOD,
    max_points: int | None = Query(None, ge=50, le=5000, description="Downsample for charting"),
    service: AnalysisService = Depends(analysis_service),
):
    """Daily history for a pair written as "AUD-JPY", "AUD/JPY" or "AUDJPY" (rates are quote per 1 base)."""
    m = re.fullmatch(r"([A-Za-z]{3})[-/_]?([A-Za-z]{3})", currency_pair)
    if not m:
        raise HTTPException(status_code=400, detail="Write the pair as BASE-QUOTE, e.g. AUD-JPY.")
    base, quote = m.group(1).upper(), m.group(2).upper()
    known = all_currency_codes()
    for code in (base, quote):
        if code not in known:
            raise HTTPException(status_code=404, detail=f"Unknown currency: {code}")
    if base == quote:
        raise HTTPException(status_code=400, detail="Choose two different currencies.")
    return await service.history(base, quote, resolve_period(period), max_points)
