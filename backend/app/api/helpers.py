import secrets

from fastapi import Request

from backend.app.core.clock import iso_z, utc_now


def envelope(request: Request, data, *, pagination=None, search=None):
    meta = {"request_id": getattr(request.state, "request_id", "req_" + secrets.token_hex(10)), "generated_at": iso_z(utc_now())}
    if pagination is not None:
        meta["pagination"] = pagination
    if search is not None:
        meta["search"] = search
    return {"data": data, "meta": meta}


def pagination(page: int, per_page: int, total: int) -> dict:
    return {"page": page, "per_page": per_page, "total": total, "has_next": page * per_page < total}
