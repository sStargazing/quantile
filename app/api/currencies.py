from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import analysis_service, resolve_base
from app.config.destinations import (
    DEFAULT_BASE,
    DEFAULT_PERIOD,
    DESTINATIONS,
    HOME_CURRENCIES,
    PERIODS,
    all_currency_codes,
)
from app.models import schemas
from app.services.analysis import AnalysisService

router = APIRouter(prefix="/api", tags=["reference data"])


@router.get("/currencies", response_model=list[schemas.HomeCurrencyOut])
def currencies():
    """Home currencies a traveller can choose from."""
    return [schemas.HomeCurrencyOut(**h.__dict__) for h in HOME_CURRENCIES]


@router.get("/destinations", response_model=list[schemas.DestinationOut])
def destinations():
    return [schemas.DestinationOut(**{k: getattr(d, k) for k in schemas.DestinationOut.model_fields}) for d in DESTINATIONS]


@router.get("/options", response_model=schemas.OptionsResponse)
def options():
    """Everything the frontend needs to build its selectors."""
    return schemas.OptionsResponse(
        home_currencies=currencies(),
        periods=[schemas.PeriodOut(key=p.key, label=p.label, years=p.years) for p in PERIODS],
        default_base=DEFAULT_BASE,
        default_period=DEFAULT_PERIOD,
    )


@router.get("/convert", response_model=schemas.ConvertResponse)
async def convert(
    to: str,
    amount: float = Query(gt=0, description="Amount in the base currency"),
    base: str = DEFAULT_BASE,
    service: AnalysisService = Depends(analysis_service),
):
    """Convert an amount at the latest reference rate (the original Quantile calculator)."""
    base = resolve_base(base).code
    to = to.upper()
    if to not in all_currency_codes():
        raise HTTPException(status_code=404, detail=f"Unknown currency: {to}")
    if to == base:
        raise HTTPException(status_code=400, detail="Choose two different currencies.")
    rate, day = await service.latest_rate(base, to)
    return schemas.ConvertResponse(base=base, to=to, amount=amount, rate=rate, result=round(amount * rate, 2), date=day)
