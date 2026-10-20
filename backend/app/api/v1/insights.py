import csv
import io

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_session
from backend.app.api.helpers import envelope
from backend.app.schemas.common import SuccessEnvelope
from backend.app.schemas.insights import InsightQuality, InsightSeries, ReleaseDetail, RepositoryInsights
from backend.app.services.insights import repository_insights, repository_release_detail

router = APIRouter(prefix="/repositories", tags=["insights"])


@router.get("/{repository_id}/insights", response_model=SuccessEnvelope[RepositoryInsights])
def insights(repository_id: int, request: Request, session: Session = Depends(get_session)):
    return envelope(request, repository_insights(session, repository_id))


@router.get("/{repository_id}/releases/{release_id}", response_model=SuccessEnvelope[ReleaseDetail])
def release_detail(repository_id: int, request: Request, release_id: int = Path(gt=0, lt=10**20), session: Session = Depends(get_session)):
    return envelope(request, repository_release_detail(session, repository_id, release_id))


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
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="githubda_insights_{repository_id}.csv"'})
