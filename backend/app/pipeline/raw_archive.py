import gzip
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings


def archive_json(repository_id: int, task_id: str, kind: str, value: Any) -> str:
    root = get_settings().raw_data_path
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    relative = Path(str(repository_id)) / date / task_id / f"{kind}.json.gz"
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
