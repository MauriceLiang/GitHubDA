from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.settings import CollectionSettingsRequest, CollectionSettingsResponse
from backend.app.services.application_settings import get_github_max_pages, save_github_max_pages


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SuccessEnvelope[CollectionSettingsResponse])
def get_collection_settings(request: Request, session: Session = Depends(get_session)):
    return envelope(request, {"github_max_pages": get_github_max_pages(session)})


@router.post("", response_model=SuccessEnvelope[CollectionSettingsResponse])
def update_collection_settings(
    payload: CollectionSettingsRequest,
    request: Request,
    session: Session = Depends(get_session),
):
    value = save_github_max_pages(session, payload.github_max_pages)
    return envelope(request, {"github_max_pages": value})
