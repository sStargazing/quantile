from fastapi import APIRouter, Depends

from app.api.deps import analysis_service, resolve_base, resolve_period
from app.config.destinations import DEFAULT_BASE, DEFAULT_PERIOD
from app.models import schemas
from app.services.analysis import AnalysisService

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/leaderboard", response_model=schemas.LeaderboardResponse)
async def leaderboard(
    base: str = DEFAULT_BASE,
    period: str = DEFAULT_PERIOD,
    service: AnalysisService = Depends(analysis_service),
):
    """All destinations ranked by Quantile Score for a home currency and comparison period."""
    return await service.leaderboard(resolve_base(base), resolve_period(period))
