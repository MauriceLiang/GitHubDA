"""Validate a featured bundle and print a machine-readable quality summary."""

import argparse
import json
import sys
from pathlib import Path

from backend.app.services.dataset_import import BundleError, verify_dataset_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        result = verify_dataset_bundle(args.bundle)
        result["quality_check"] = "passed"
        result["checks"] = ["schema", "required files", "SHA-256", "member count", "repository references", "JSONL/GZIP integrity"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, BundleError) as exc:
        print(f"dataset validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
