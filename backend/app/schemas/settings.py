from pydantic import Field

from backend.app.schemas.common import DTO


class CollectionSettingsRequest(DTO):
    github_max_pages: int = Field(ge=1, le=100)


class CollectionSettingsResponse(DTO):
    github_max_pages: int = Field(ge=1, le=100)
