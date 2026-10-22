from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.schemas.analytics import DatasetListResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.services.analytics import get_datasets
from backend.app.services.dataset_import import dataset_coverage, featured_bundle_archive, featured_status, import_featured_bundle


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=SuccessEnvelope[DatasetListResponse])
def datasets(request: Request, session: Session = Depends(get_session)):
    return envelope(request, {"items": get_datasets(session)})


@router.get("/featured/status", response_model=SuccessEnvelope[dict[str, Any]])
def get_featured_status(request: Request, session: Session = Depends(get_session)):
    return envelope(request, featured_status(session))


@router.post("/featured/import", response_model=SuccessEnvelope[dict[str, Any]])
def import_featured(request: Request, session: Session = Depends(get_session)):
    return envelope(request, import_featured_bundle(session))


@router.get("/featured/export", response_class=FileResponse)
def export_featured():
    path, filename = featured_bundle_archive()
    return FileResponse(path, media_type="application/zip", filename=filename, headers={"Cache-Control": "no-store"})


@router.get("/{dataset_id}/coverage", response_model=SuccessEnvelope[dict[str, Any]])
def get_dataset_coverage(dataset_id: str, request: Request, session: Session = Depends(get_session)):
    return envelope(request, dataset_coverage(session, dataset_id))
