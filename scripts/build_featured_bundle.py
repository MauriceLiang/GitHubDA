"""Build the sanitized, versioned featured dataset directory from local DB data."""

import argparse
import json
import sys
from pathlib import Path

from backend.app.core.exceptions import AppError
from backend.app.persistence.db import SessionLocal
from backend.app.services.dataset_bundle import build_featured_bundle
from backend.app.services.dataset_import import BUNDLE_ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="featured-v1.0.0")
    parser.add_argument("--output", type=Path, default=BUNDLE_ROOT)
    parser.add_argument("--force", action="store_true", help="replace an existing versioned data bundle")
    args = parser.parse_args()
    session = SessionLocal()
    try:
        print(json.dumps(build_featured_bundle(session, args.version, args.output, force=args.force), ensure_ascii=False, indent=2))
    except (OSError, ValueError, AppError) as exc:
        print(f"featured bundle build failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        session.close()


if __name__ == "__main__":
    main()
