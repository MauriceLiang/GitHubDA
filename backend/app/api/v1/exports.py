from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.core.exceptions import AppError
from backend.app.services.analytics import export_repositories


router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/repositories.csv")
def export_csv(
    request: Request,
    scope: Literal["research", "library"],
    dataset_id: str | None = None,
    language: str | None = None,
    session: Session = Depends(get_session),
):
    content, filename = export_repositories(session, scope, dataset_id, language)
    return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
