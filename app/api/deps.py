"""Shared request validation and service access for route handlers."""

from fastapi import HTTPException, Request

from app.config.destinations import HomeCurrency, Period, get_home_currency, get_period, HOME_CURRENCIES, PERIODS
from app.services.analysis import AnalysisService


def analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis


def resolve_base(base: str) -> HomeCurrency:
    home = get_home_currency(base)
    if home is None:
        options = ", ".join(h.code for h in HOME_CURRENCIES)
        raise HTTPException(status_code=400, detail=f"Unsupported home currency '{base}'. Choose one of: {options}.")
    return home


def resolve_period(period: str) -> Period:
    p = get_period(period)
    if p is None:
        options = ", ".join(x.key for x in PERIODS)
        raise HTTPException(status_code=400, detail=f"Unsupported period '{period}'. Choose one of: {options}.")
    return p
