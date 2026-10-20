"""Validate external objects without retaining emails, bodies or user payloads."""
import re
from datetime import datetime
from typing import Any

from backend.app.core.clock import parse_github_datetime

MODULE_TYPES = {"commits": "commit", "issues": "issue", "pulls": "pull_request", "releases": "release"}


def event_date(value: Any) -> datetime | None:
    # Reject timezone-free external dates and impossible/unbounded dates.
    if not isinstance(value, str) or len(value) > 40 or not re.search(r"(Z|[+-]\d\d:\d\d)$", value):
        return None
    parsed = parse_github_datetime(value)
    return parsed if parsed and 1970 <= parsed.year <= 2100 else None


def normalize_events(module: str, rows: list[dict]) -> tuple[list[dict], dict]:
    unique = {}
    rejected = filtered = duplicate = invalid_times = 0
    for row in rows:
        if module == "issues" and "pull_request" in row:
            filtered += 1
            continue
        if module == "releases" and any(key in row and type(row[key]) is not bool for key in ("draft", "prerelease")):
            rejected += 1
            continue
        identifier = row.get("sha") if module == "commits" else row.get("id")
        valid_id = isinstance(identifier, str) and bool(re.fullmatch(r"[a-fA-F0-9]{40,64}", identifier)) if module == "commits" else type(identifier) is int and 0 < identifier < 10**20
        if not valid_id:
            rejected += 1
            continue
        event = {"event_type": MODULE_TYPES[module], "source_item_id": str(identifier)}
        for field in ("created_at", "closed_at", "merged_at", "published_at", "updated_at"):
            event[field] = event_date(row.get(field))
        if module == "commits":
            commit = row.get("commit")
            committer = commit.get("committer") if isinstance(commit, dict) else None
            event["event_at"] = event_date(committer.get("date")) if isinstance(committer, dict) else None
        else:
            event["event_at"] = event[{"issues": "closed_at", "pulls": "merged_at", "releases": "published_at"}[module]]
        # An open issue or unmerged PR legitimately has no terminal timestamp.
        expected_time = module == "commits" or (module == "releases" and not row.get("draft")) or row.get("closed_at") is not None or row.get("merged_at") is not None
        if expected_time and event["event_at"] is None and not (module == "pulls" and row.get("merged_at") is None):
            invalid_times += 1
        event["is_draft"] = row.get("draft") is True if module == "releases" else None
        event["is_prerelease"] = row.get("prerelease") is True if module == "releases" else None
        author = row.get("author")
        author_id = author.get("id") if isinstance(author, dict) else None
        event["author_key"] = f"github:{author_id}" if module == "commits" and type(author_id) is int and author_id > 0 else None
        if str(identifier) in unique:
            duplicate += 1
        unique[str(identifier)] = event
    return list(unique.values()), {"observed_records": len(rows), "accepted_events": len(unique), "rejected_records": rejected, "invalid_event_times": invalid_times, "filtered_pr_records": filtered, "duplicate_records": duplicate}
