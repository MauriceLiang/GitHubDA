"""Queue bounded repository activity collection for an existing dataset."""

import argparse
import json
import sys

from sqlalchemy import select

from backend.app.core.exceptions import AppError
from backend.app.persistence.db import SessionLocal
from backend.app.persistence.models import Dataset, DatasetRepository
from backend.app.services.repositories import make_task


def queue(dataset_id: str, scope_kind: str) -> dict:
    session = SessionLocal()
    try:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise ValueError(f"dataset not found: {dataset_id}")
        memberships = session.scalars(select(DatasetRepository).where(DatasetRepository.dataset_id == dataset_id).order_by(DatasetRepository.repository_id)).all()
        if not memberships:
            raise ValueError(f"dataset has no members: {dataset_id}")
        queued = []
        for member in memberships:
            task = make_task(session, member.repository_id, "deep", scope_kind=scope_kind)
            queued.append({"repository_id": member.repository_id, "task_id": task.task_id, "status": task.status, "scope_kind": task.scope_kind})
        session.commit()
        return {"dataset_id": dataset_id, "scope_kind": scope_kind, "queued_count": len(queued), "tasks": queued, "note": "任务已排队；实际 GitHub API 请求由已启动的 Worker 执行。"}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_id", help="existing dataset ID, for example featured-default")
    parser.add_argument("--scope", choices=("quick", "window"), default="quick")
    args = parser.parse_args()
    try:
        print(json.dumps(queue(args.dataset_id, args.scope), ensure_ascii=False, indent=2))
    except (ValueError, AppError) as exc:
        print(f"dataset collection queue failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
