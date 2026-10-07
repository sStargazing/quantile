"""Quantile FastAPI application.

Run with:  uvicorn app.main:app --reload
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import countries, currencies, leaderboard
from app.config.destinations import PERIODS, all_cpi_series, all_currency_codes, get_destination
from app.providers.base import ProviderError
from app.providers.frankfurter import FrankfurterProvider
from app.providers.imf import ImfCpiProvider
from app.services.analysis import AnalysisService
from app.services.cache import FileCache
from app.services.exchange_rates import ExchangeRateService
from app.services.inflation import InflationService
from app.settings import ROOT_DIR, settings

log = logging.getLogger("quantile")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = FileCache(settings.cache_dir)
    cache.prune(keep_expired_for=30 * 24 * 60 * 60)
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        fx = ExchangeRateService(FrankfurterProvider(client, settings.fx_api_base_url), cache, all_currency_codes())
        inflation = InflationService(ImfCpiProvider(client, settings.cpi_api_base_url), cache, all_cpi_series())
        app.state.analysis = AnalysisService(fx, inflation)

        prewarm = None
        if settings.prewarm_on_startup:
            longest = max(PERIODS, key=lambda p: p.years)

            async def warm():
                try:
                    await app.state.analysis.prewarm(longest)
                    log.info("data cache warmed")
                except Exception:
                    log.warning("could not prewarm data cache", exc_info=True)

            prewarm = asyncio.create_task(warm())
        yield
        if prewarm and not prewarm.done():
            prewarm.cancel()


app = FastAPI(title="Quantile", description="Where does my money go further than usual?", lifespan=lifespan)
app.include_router(currencies.router)
app.include_router(leaderboard.router)
app.include_router(countries.router)
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
templates = Jinja2Templates(directory=ROOT_DIR / "templates")


@app.exception_handler(ProviderError)
async def provider_error(request: Request, exc: ProviderError):
    log.warning("provider error: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": f"The {exc.source} isn't responding and Quantile has no saved copy of this data yet. "
            "Retry in a minute."
        },
    )


# ---- pages -------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def leaderboard_page(request: Request):
    return templates.TemplateResponse(request, "leaderboard.html", {"active": "leaderboard"})


@app.get("/country/{slug}", response_class=HTMLResponse, include_in_schema=False)
def country_page(request: Request, slug: str):
    dest = get_destination(slug)
    if dest is None:
        raise HTTPException(status_code=404, detail="Unknown destination")
    return templates.TemplateResponse(request, "country.html", {"active": "leaderboard", "destination": dest})


@app.get("/converter", response_class=HTMLResponse, include_in_schema=False)
def converter_page(request: Request):
    return templates.TemplateResponse(request, "converter.html", {"active": "converter"})
