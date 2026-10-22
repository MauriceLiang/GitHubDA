import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_github_client, get_session
from backend.app.api.helpers import envelope, pagination
from backend.app.core.exceptions import AppError
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.insights import ClosedIssueDetail, ClosedIssuePage, CommitActivityPage, InsightQuality, InsightSeries, OnlineIssueDetail, OnlinePullRequestDetail, PullRequestDetail, PullRequestPage, ReleaseDetail, RepositoryInsights
from backend.app.services.insights import repository_closed_issue_detail, repository_closed_issue_online_detail, repository_closed_issues, repository_commit_activity, repository_insights, repository_pull_request_detail, repository_pull_request_online_detail, repository_pull_requests, repository_release_detail
from backend.app.integrations.github.client import GitHubClient

router = APIRouter(prefix="/repositories", tags=["insights"])


@router.get("/{repository_id}/insights", response_model=SuccessEnvelope[RepositoryInsights])
def insights(repository_id: int, request: Request, session: Session = Depends(get_session)):
    return envelope(request, repository_insights(session, repository_id))


@router.get("/{repository_id}/releases/{release_id}", response_model=SuccessEnvelope[ReleaseDetail])
def release_detail(repository_id: int, request: Request, release_id: int = Path(gt=0, lt=10**20), session: Session = Depends(get_session)):
    return envelope(request, repository_release_detail(session, repository_id, release_id))


@router.get("/{repository_id}/commits", response_model=SuccessEnvelope[CommitActivityPage])
def commit_activity(
    repository_id: int,
    request: Request,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=100),
    week_start: date | None = Query(default=None),
    session: Session = Depends(get_session),
):
    result = repository_commit_activity(session, repository_id, page=page, per_page=per_page, search=search, week_start=week_start)
    items = result["items"]
    total = result["total"]
    result.update({"items": items, "page": page, "per_page": per_page})
    return envelope(request, result, pagination=pagination(page, per_page, total), search={"q": search} if search else None)


@router.get("/{repository_id}/issues", response_model=SuccessEnvelope[ClosedIssuePage])
def closed_issues(
    repository_id: int,
    request: Request,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=100),
    session: Session = Depends(get_session),
):
    result = repository_closed_issues(session, repository_id, search)
    items = result["items"]
    total = len(items)
    result.update({"items": items[(page - 1) * per_page : page * per_page], "page": page, "per_page": per_page, "total": total})
    return envelope(request, result, pagination=pagination(page, per_page, total), search={"q": search} if search else None)


@router.get("/{repository_id}/issues/export.csv")
def export_closed_issues(repository_id: int, search: str = Query(default="", max_length=100), session: Session = Depends(get_session)):
    result = repository_closed_issues(session, repository_id, search)
    if not result["available"]:
        raise AppError(409, "ISSUE_ARCHIVE_UNAVAILABLE", result["note"])
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["issue_number", "title", "created_at", "closed_at", "duration_days", "url"])
    for item in result["items"]:
        row = [item["number"], item["title"], item["created_at"], item["closed_at"], item["duration_days"], item["url"]]
        writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for value in row])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="repovantage_issues_{repository_id}.csv"'})


@router.get("/{repository_id}/issues/{issue_number}", response_model=SuccessEnvelope[ClosedIssueDetail])
def closed_issue_detail(repository_id: int, request: Request, issue_number: int = Path(gt=0, lt=10**10), session: Session = Depends(get_session)):
    return envelope(request, repository_closed_issue_detail(session, repository_id, issue_number))


@router.get("/{repository_id}/issues/{issue_number}/online", response_model=SuccessEnvelope[OnlineIssueDetail])
def online_issue_detail(repository_id: int, request: Request, issue_number: int = Path(gt=0, lt=10**10), session: Session = Depends(get_session), github: GitHubClient = Depends(get_github_client)):
    return envelope(request, repository_closed_issue_online_detail(session, repository_id, issue_number, github))


@router.get("/{repository_id}/pull-requests", response_model=SuccessEnvelope[PullRequestPage])
def pull_requests(
    repository_id: int,
    request: Request,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=100),
    session: Session = Depends(get_session),
):
    result = repository_pull_requests(session, repository_id, search)
    items = result["items"]
    total = len(items)
    result.update({"items": items[(page - 1) * per_page : page * per_page], "page": page, "per_page": per_page, "total": total})
    return envelope(request, result, pagination=pagination(page, per_page, total), search={"q": search} if search else None)


@router.get("/{repository_id}/pull-requests/export.csv")
def export_pull_requests(repository_id: int, search: str = Query(default="", max_length=100), session: Session = Depends(get_session)):
    result = repository_pull_requests(session, repository_id, search)
    if not result["available"]:
        raise AppError(409, "PULL_REQUEST_ARCHIVE_UNAVAILABLE", result["note"])
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["pull_number", "title", "state", "created_at", "closed_at", "merged_at", "merge_duration_days", "draft", "comments_count", "url"])
    for item in result["items"]:
        row = [item["number"], item["title"], item["state"], item["created_at"], item["closed_at"], item["merged_at"], item["duration_days"], item["draft"], item["comments_count"], item["url"]]
        writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for value in row])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="repovantage_pull_requests_{repository_id}.csv"'})


@router.get("/{repository_id}/pull-requests/{pull_number}", response_model=SuccessEnvelope[PullRequestDetail])
def pull_request_detail(repository_id: int, request: Request, pull_number: int = Path(gt=0, lt=10**10), session: Session = Depends(get_session)):
    return envelope(request, repository_pull_request_detail(session, repository_id, pull_number))


@router.get("/{repository_id}/pull-requests/{pull_number}/online", response_model=SuccessEnvelope[OnlinePullRequestDetail])
def online_pull_request_detail(repository_id: int, request: Request, pull_number: int = Path(gt=0, lt=10**10), session: Session = Depends(get_session), github: GitHubClient = Depends(get_github_client)):
    return envelope(request, repository_pull_request_online_detail(session, repository_id, pull_number, github))


@router.get("/{repository_id}/insights/series", response_model=SuccessEnvelope[InsightSeries])
def insight_series(repository_id: int, request: Request, metric: str = Query(pattern="^(commits_weekly|issues_closed_weekly|prs_merged_weekly)$"), session: Session = Depends(get_session)):
    result = repository_insights(session, repository_id)
    key = {"commits_weekly": "commit_activity", "issues_closed_weekly": "issue_resolution", "prs_merged_weekly": "pr_merges"}[metric]
    value = result["insights"].get(key, {})
    return envelope(request, {"metric": metric, "window_start": result["window_start"], "window_end": result["window_end"], "timezone": "UTC", "unit": "events", "points": value.get("weekly", []), "notes": result["limitations"]})


@router.get("/{repository_id}/insights/quality", response_model=SuccessEnvelope[InsightQuality])
def insight_quality(repository_id: int, request: Request, session: Session = Depends(get_session)):
    result = repository_insights(session, repository_id)
    return envelope(request, {key: result[key] for key in ("run_id", "metric_version", "analyzed_at", "sources", "limitations")} | {"metrics": {key: value["quality"] for key, value in result["insights"].items()}})


@router.get("/{repository_id}/insights/export.csv")
def export_insights(repository_id: int, session: Session = Depends(get_session)):
    result = repository_insights(session, repository_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["repository_id", "run_id", "metric_version", "metric", "unit", "window_start", "window_end", "bucket_start", "bucket_end", "value", "quality", "valid_samples", "source_task_ids"])
    for key, value in result["insights"].items():
        records = []
        for field in ("median_hours", "p75_hours", "p90_hours", "median_interval_days", "recent_4w", "previous_4w", "delta", "change_rate_pct"):
            if field in value:
                records.append({"metric": key + "." + field, "unit": "percent" if field == "change_rate_pct" else "commits" if field in {"recent_4w", "previous_4w", "delta"} else value["unit"], "start": None, "end": None, "value": value[field], "quality": value["quality"]["status"]})
        records.extend({**point, "metric": {"commit_activity": "commits_weekly", "issue_resolution": "issues_closed_weekly", "pr_merges": "prs_merged_weekly"}[key], "unit": "events"} for point in value.get("weekly", []))
        for point in records:
            row = [repository_id, result["run_id"], result["metric_version"], point["metric"], point["unit"], value["window_start"], value["window_end"], point["start"], point["end"], point["value"], point["quality"], value["quality"]["valid_samples"], ";".join(result["source_task_ids"])]
            writer.writerow(["'" + item if isinstance(item, str) and item.startswith(("=", "+", "-", "@", "\t", "\r")) else item for item in row])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="repovantage_insights_{repository_id}.csv"'})
