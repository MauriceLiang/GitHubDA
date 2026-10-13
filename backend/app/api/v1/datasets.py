from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.schemas.analytics import DatasetListResponse
from backend.app.schemas.common import SuccessEnvelope
from backend.app.services.analytics import get_datasets


router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=SuccessEnvelope[DatasetListResponse])
def datasets(request: Request, session: Session = Depends(get_session)):
    return envelope(request, {"items": get_datasets(session)})
