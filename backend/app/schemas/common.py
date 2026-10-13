from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_serializer


T = TypeVar("T")


class Pagination(BaseModel):
    page: int
    per_page: int
    total: int
    has_next: bool


class ApiMeta(BaseModel):
    request_id: str
    generated_at: str
    pagination: Pagination | None = None
    search: dict[str, Any] | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}


class SuccessEnvelope(BaseModel, Generic[T]):
    data: T
    meta: ApiMeta


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
