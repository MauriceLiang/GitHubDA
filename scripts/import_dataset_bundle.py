"""Import a validated featured dataset directory or ZIP into the configured DB."""

import argparse
import json
import sys
from pathlib import Path

from backend.app.core.exceptions import AppError
from backend.app.persistence.db import SessionLocal
from backend.app.services.dataset_import import BundleError, import_featured_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="bundle directory or ZIP")
    args = parser.parse_args()
    session = SessionLocal()
    try:
        print(json.dumps(import_featured_bundle(session, args.source), ensure_ascii=False, indent=2))
    except (OSError, BundleError, AppError) as exc:
        print(f"dataset bundle import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        session.close()


if __name__ == "__main__":
    main()
