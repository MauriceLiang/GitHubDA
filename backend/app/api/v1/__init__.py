from fastapi import APIRouter, Depends

from backend.app.api.dependencies import require_internal_api_key
from backend.app.api.v1 import analytics, datasets, exports, github, insights, library, repositories, settings, system, tasks


router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_internal_api_key)])
for child in (system.router, insights.router, github.router, library.router, repositories.router, settings.router, tasks.router, datasets.router, analytics.router, exports.router):
    router.include_router(child)
