from typing import Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.core.exceptions import AppError
from backend.app.schemas.analytics import ComparisonResponse, DataQualityResponse, OverviewResponse, StatisticsResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.repositories import ComparisonRequest
from backend.app.services.analytics import compare_repositories, data_quality, overview, research_statistics


router = APIRouter(tags=["analytics"])


@router.get("/overview", response_model=SuccessEnvelope[OverviewResponse])
def get_overview(request: Request, scope: Literal["research", "library"], dataset_id: str | None = None, language: str | None = None, session: Session = Depends(get_session)):
    return envelope(request, overview(session, scope, dataset_id, language))


@router.get("/research/statistics", response_model=SuccessEnvelope[StatisticsResponse])
def get_research_statistics(
    request: Request,
    dataset_id: str,
    language: str | None = None,
    group_by: Literal["language", "star_tier", "age_tier"] = "language",
    session: Session = Depends(get_session),
):
    return envelope(request, research_statistics(session, dataset_id, language, group_by))


@router.get("/research/data-quality", response_model=SuccessEnvelope[DataQualityResponse])
def get_data_quality(request: Request, dataset_id: str, session: Session = Depends(get_session)):
    return envelope(request, data_quality(session, dataset_id))


@router.post("/comparisons", response_model=SuccessEnvelope[ComparisonResponse])
def compare(request: Request, body: ComparisonRequest, session: Session = Depends(get_session)):
    return envelope(request, compare_repositories(session, body.repository_ids, body.depth))


@router.post("/comparisons/insights")
def compare_activity_insights(request: Request, body: ComparisonRequest, session: Session = Depends(get_session)):
    from backend.app.services.insight_comparison import compare_insights
    return envelope(request, compare_insights(session, body.repository_ids))


@router.get("/research/insights")
def get_research_insights(request: Request, dataset_id: str, session: Session = Depends(get_session)):
    from backend.app.services.insight_comparison import research_insights
    return envelope(request, research_insights(session, dataset_id))
