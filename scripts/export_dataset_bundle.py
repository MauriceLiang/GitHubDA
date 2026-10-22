"""Export a verified featured dataset directory as a versioned ZIP."""

import argparse
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from backend.app.services.dataset_import import BundleError, verify_dataset_bundle


def export(source: Path, output: Path, *, force: bool = False) -> dict:
    verified = verify_dataset_bundle(source)
    source = source.expanduser().resolve()
    if source.is_file():
        raise ValueError("ZIP export source must be a verified directory")
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not force:
        raise FileExistsError(f"{output} already exists; pass --force to replace it")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_symlink():
                    raise BundleError("bundle export refuses symlinks")
                if path.is_file():
                    archive.write(path, path.relative_to(source).as_posix())
        os.replace(temporary, output)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return {"output": str(output), "dataset_id": verified["dataset_id"], "version": verified["version"], "bundle_hash": verified["bundle_hash"], "bytes": output.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        verified = verify_dataset_bundle(args.source)
        output = args.output or Path(f"repovantage-dataset-{verified['version']}.zip")
        print(json.dumps(export(args.source, output, force=args.force), ensure_ascii=False, indent=2))
    except (OSError, ValueError, BundleError) as exc:
        print(f"dataset bundle export failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
