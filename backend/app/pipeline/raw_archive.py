import gzip
import json
import os
import tempfile
import zlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings


def archive_json(
    repository_id: int,
    task_id: str,
    kind: str,
    value: Any,
    *,
    root: Path | None = None,
    archive_date: date | None = None,
) -> str:
    root = (root or get_settings().raw_data_path).resolve()
    day = (archive_date or datetime.now(UTC).date()).strftime("%Y-%m-%d")
    relative = Path(str(repository_id)) / day / task_id / f"{kind}.json.gz"
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError("archive path escapes configured raw data directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".archive-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as raw_file:
            with gzip.GzipFile(fileobj=raw_file, mode="wb") as compressed:
                compressed.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return str(relative)


def read_archive(relative: str, *, max_compressed_bytes=16_000_000, max_bytes=64_000_000) -> dict:
    """Bounded, data-only replay. No pickle, paths or executable archive members."""
    root = get_settings().raw_data_path.resolve()
    candidate = Path(relative)
    target = (root / candidate).resolve()
    if candidate.is_absolute() or not target.is_relative_to(root) or target.suffixes[-2:] != [".json", ".gz"]:
        raise ValueError("archive path escapes configured raw data directory or has invalid format")
    if target.stat().st_size > max_compressed_bytes:
        raise ValueError("compressed archive exceeds size limit")
    try:
        with gzip.open(target, "rb") as handle:
            payload = handle.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("decompressed archive exceeds size limit")
        value = json.loads(payload)
    except (OSError, EOFError, zlib.error, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid gzip JSON archive") from exc
    if not isinstance(value, dict):
        raise ValueError("archive root must be an object")
    return value
