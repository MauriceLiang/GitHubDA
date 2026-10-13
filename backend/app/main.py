import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.api.v1 import router as v1_router
from backend.app.core.exceptions import AppError
from backend.app.persistence.db import SessionLocal
from backend.app.schemas.common import ErrorResponse
from backend.app.services.repositories import ensure_default_datasets


logger = logging.getLogger("githubda.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    session = SessionLocal()
    try:
        ensure_default_datasets(session)
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Database schema is missing; run `alembic upgrade head` before starting the API")
        raise
    finally:
        session.close()
    yield


app = FastAPI(title="GitHubDA API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if supplied.startswith("req_") and len(supplied) <= 80 and supplied.replace("_", "").replace("-", "").isalnum() else f"req_{secrets.token_hex(12)}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _error(request: Request, status_code: int, code: str, message: str, details: dict | None = None):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}, "request_id": getattr(request.state, "request_id", "req_unknown")},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return _error(request, exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    fields = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
        fields.append({"field": location, "message": item.get("msg", "参数无效")})
    return _error(request, 422, "VALIDATION_ERROR", "请求参数不符合接口约定", {"fields": fields})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    mapping = {
        401: ("UNAUTHORIZED_CLIENT", "内部 API Key 无效"),
        404: ("RESOURCE_NOT_FOUND", "请求的资源不存在"),
        409: ("CONFLICTING_OPERATION", "当前状态不允许此操作"),
        503: ("BACKEND_UNAVAILABLE", "后端暂不可用"),
    }
    code, message = mapping.get(exc.status_code, ("BACKEND_UNAVAILABLE", "请求无法处理"))
    return _error(request, exc.status_code, code, message)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database operation failed", exc_info=exc)
    return _error(request, 503, "BACKEND_UNAVAILABLE", "数据库暂不可用")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


app.include_router(v1_router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    error_schema = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")
    definitions = error_schema.pop("$defs", {})
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components.update(definitions)
    components["ErrorResponse"] = error_schema
    error_response = {"description": "统一错误响应", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            responses = operation.setdefault("responses", {})
            if "422" in responses:
                responses["422"] = error_response
            if path.startswith("/api/v1/"):
                responses.setdefault("401", error_response)
                responses.setdefault("429", error_response)
                responses.setdefault("502", error_response)
                responses.setdefault("503", error_response)
                responses.setdefault("504", error_response)
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
