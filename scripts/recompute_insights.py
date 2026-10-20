"""Default is a non-mutating local preview. --apply explicitly persists a replay."""
import argparse
import json

from backend.app.persistence.db import SessionLocal
from backend.app.pipeline.archive_replay import replay_activity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        try:
            result = replay_activity(session, args.repository_id, apply=args.apply)
            if args.apply:
                session.commit()
        except (ValueError, OSError) as exc:
            parser.exit(1, f"无法回放：{exc}\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
