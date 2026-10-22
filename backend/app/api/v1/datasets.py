from typing import Any

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.schemas.analytics import DatasetListResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.services.analytics import get_datasets
from backend.app.services.dataset_import import dataset_coverage, featured_bundle_archive, featured_status, queue_featured_import


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=SuccessEnvelope[DatasetListResponse])
def datasets(request: Request, session: Session = Depends(get_session)):
    return envelope(request, {"items": get_datasets(session)})


@router.get("/featured/status", response_model=SuccessEnvelope[dict[str, Any]])
def get_featured_status(request: Request, session: Session = Depends(get_session)):
    return envelope(request, featured_status(session))


@router.post("/featured/import", response_model=SuccessEnvelope[dict[str, Any]], status_code=202)
def import_featured(
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    session: Session = Depends(get_session),
):
    result = queue_featured_import(session, idempotency_key)
    response.status_code = 200 if result.get("already_current") else 202
    return envelope(request, result)


@router.get("/featured/export", response_class=FileResponse)
def export_featured():
    path, filename = featured_bundle_archive()
    return FileResponse(path, media_type="application/zip", filename=filename, headers={"Cache-Control": "no-store"})


@router.get("/{dataset_id}/coverage", response_model=SuccessEnvelope[dict[str, Any]])
def get_dataset_coverage(dataset_id: str, request: Request, session: Session = Depends(get_session)):
    return envelope(request, dataset_coverage(session, dataset_id))
