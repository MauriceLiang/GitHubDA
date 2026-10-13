import json

from sqlalchemy import text

from backend.app.persistence.db import SessionLocal


def main() -> None:
    session = SessionLocal()
    try:
        foreign_key_errors = session.execute(text("PRAGMA foreign_key_check")).all()
        orphan_memberships = session.execute(text("""
            SELECT dataset_repositories.dataset_id, dataset_repositories.repository_id
            FROM dataset_repositories
            LEFT JOIN datasets ON datasets.dataset_id = dataset_repositories.dataset_id
            LEFT JOIN repositories ON repositories.repository_id = dataset_repositories.repository_id
            WHERE datasets.dataset_id IS NULL OR repositories.repository_id IS NULL
        """)).all()
        report = {"foreign_key_errors": [list(row) for row in foreign_key_errors], "orphan_memberships": [list(row) for row in orphan_memberships]}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if foreign_key_errors or orphan_memberships:
            raise SystemExit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
