import csv
import io
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.core.exceptions import AppError
from backend.app.services.analytics import compare_repositories, export_repositories


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


@router.get("/comparison.csv")
def export_comparison_csv(
    request: Request,
    repository_ids: str = Query(min_length=3, max_length=40),
    depth: Literal["basic", "deep"] = "basic",
    session: Session = Depends(get_session),
):
    try:
        ids = [int(value) for value in repository_ids.split(",")]
    except ValueError as exc:
        raise AppError(422, "VALIDATION_ERROR", "repository_ids 必须是仓库编号列表", {"fields": [{"field": "repository_ids", "message": "仅接受逗号分隔的整数"}]}) from exc
    if not 2 <= len(ids) <= 5 or len(set(ids)) != len(ids) or any(value <= 0 for value in ids):
        raise AppError(422, "VALIDATION_ERROR", "请选择 2–5 个不同的仓库", {"fields": [{"field": "repository_ids", "message": "数量必须为 2–5 且编号不能重复"}]})

    comparison = compare_repositories(session, ids, depth)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["仓库", "Stars", "Forks", "仓库年龄（天）", "近 90 天提交", "近 90 天关闭 Issues", "近 90 天合并 PR", "近一年 Release", "数据覆盖"])
    for repo in comparison["repositories"]:
        metrics = repo["metrics"]
        writer.writerow([repo["full_name"], metrics.get("stars"), metrics.get("forks"), metrics.get("age_days"), metrics.get("commits_90d"), metrics.get("issues_closed_90d"), metrics.get("pr_merged_90d"), metrics.get("release_count_365d"), repo["coverage"]])
    content = "\ufeff" + output.getvalue()
    filename = f"githubda_comparison_{date.today().isoformat()}.csv"
    return Response(content=content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
