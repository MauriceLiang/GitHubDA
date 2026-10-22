"""Atomic, local-only storage for individual GitHub API pages."""
import gzip
import hashlib
import json
import os
import re
import tempfile
import zlib
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT


COLLECTED_ROOT = (PROJECT_ROOT / "data" / "collected" / "github").resolve()
MODULES = {"commits", "issues", "pulls", "releases"}
FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")


def scope_fingerprint(repository_id: int, module: str, query: dict, window_start: str, window_end: str) -> str:
    value = json.dumps(
        {"repository_id": repository_id, "module": module, "query": query, "window_start": window_start, "window_end": window_end, "schema_version": 1},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_page(repository_id: int, module: str, fingerprint: str, page_index: int, records: list[dict], raw_body: str, request_url: str, http_status: int | None) -> tuple[str, str]:
    directory = _scope_dir(repository_id, module, fingerprint)
    if type(page_index) is not int or not 1 <= page_index <= 1_000_000:
        raise ValueError("invalid page index")
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records) or not isinstance(raw_body, str):
        raise ValueError("invalid page content")
    target = directory / f"page-{page_index:06d}.json.gz"
    payload = {
        "schema_version": 1,
        "collected_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "request_url_sha256": hashlib.sha256(request_url.encode("utf-8")).hexdigest(),
        "http_status": http_status,
        "record_count": len(records),
        "raw_response": json.loads(raw_body),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    directory.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".page-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as raw_file:
            with gzip.GzipFile(fileobj=raw_file, mode="wb") as compressed:
                compressed.write(encoded)
        os.replace(temp_name, target)
        checksum_target = target.with_suffix(target.suffix + ".sha256")
        checksum_temp = checksum_target.with_name(f".{checksum_target.name}.tmp")
        checksum_temp.write_text(hashlib.sha256(target.read_bytes()).hexdigest(), encoding="ascii")
        os.replace(checksum_temp, checksum_target)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    try:
        stored_path = target.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        stored_path = str(target)
    return stored_path, hashlib.sha256(target.read_bytes()).hexdigest()


def page_paths(repository_id: int, module: str, fingerprint: str) -> list[str]:
    directory = _scope_dir(repository_id, module, fingerprint)
    if not directory.is_dir():
        return []
    paths = sorted(directory.glob("page-*.json.gz"))
    return [_stored_path(path) for path in paths if path.is_file()]


def clear_page_files(repository_id: int, module: str, fingerprint: str) -> None:
    directory = _scope_dir(repository_id, module, fingerprint)
    if directory.is_dir():
        for path in directory.glob("page-*.json.gz"):
            if path.is_file():
                path.unlink()
        for path in directory.glob("page-*.json.gz.sha256"):
            if path.is_file():
                path.unlink()


def trim_page_files(repository_id: int, module: str, fingerprint: str, page_count: int) -> list[str]:
    directory = _scope_dir(repository_id, module, fingerprint)
    if not directory.is_dir():
        return []
    paths = sorted(directory.glob("page-*.json.gz"))
    kept = []
    for expected_index, path in enumerate(paths, start=1):
        if expected_index <= page_count:
            if path.stem != f"page-{expected_index:06d}.json":
                return []
            kept.append(_stored_path(path))
        else:
            path.unlink()
            checksum = path.with_suffix(path.suffix + ".sha256")
            if checksum.exists():
                checksum.unlink()
    return kept


def read_page(relative_path: str, *, max_compressed_bytes: int = 16_000_000, max_bytes: int = 64_000_000) -> dict:
    relative = Path(relative_path)
    target = (relative if relative.is_absolute() else PROJECT_ROOT / relative).resolve()
    if not target.is_relative_to(COLLECTED_ROOT.resolve()) or target.suffixes[-2:] != [".json", ".gz"]:
        raise ValueError("page archive path escapes collected data root")
    if target.stat().st_size > max_compressed_bytes:
        raise ValueError("compressed page exceeds size limit")
    checksum = target.with_suffix(target.suffix + ".sha256")
    if not checksum.is_file():
        raise ValueError("collection page checksum is missing")
    expected_hash = checksum.read_text(encoding="ascii").strip()
    actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    if not re.fullmatch(r"[a-f0-9]{64}", expected_hash) or expected_hash != actual_hash:
        raise ValueError("collection page checksum mismatch")
    try:
        with gzip.open(target, "rb") as handle:
            payload = handle.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("decompressed page exceeds size limit")
        value = json.loads(payload)
    except (OSError, EOFError, zlib.error, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid compressed page JSON") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported page archive schema")
    if not isinstance(value.get("raw_response"), list) or any(not isinstance(row, dict) for row in value["raw_response"]):
        raise ValueError("invalid archived GitHub page records")
    return value


def iter_module_records(module_archive):
    """Yield API records from either the current page-file archive or a legacy archive."""
    if isinstance(module_archive, dict) and isinstance(module_archive.get("page_files"), list):
        paths = module_archive["page_files"]
        if len(paths) > 100_000 or any(not isinstance(path, str) for path in paths):
            raise ValueError("invalid collection page file list")
        for path in paths:
            yield from read_page(path)["raw_response"]
        return
    pages = module_archive.get("pages", []) if isinstance(module_archive, dict) else module_archive
    if not isinstance(pages, list) or len(pages) > 100_000:
        raise ValueError("invalid legacy page list")
    for raw_page in pages:
        if isinstance(raw_page, str):
            if len(raw_page) > 16_000_000:
                raise ValueError("legacy page exceeds size limit")
            try:
                records = json.loads(raw_page)
            except (ValueError, RecursionError) as exc:
                raise ValueError("invalid legacy page JSON") from exc
        else:
            records = raw_page
        if not isinstance(records, list) or len(records) > 100_000 or any(not isinstance(item, dict) for item in records):
            raise ValueError("invalid legacy page records")
        yield from records


def iter_module_pages(module_archive):
    """Yield validated page arrays without loading the full archive into memory."""
    if isinstance(module_archive, dict) and isinstance(module_archive.get("page_files"), list):
        paths = module_archive["page_files"]
        if len(paths) > 100_000 or any(not isinstance(path, str) for path in paths):
            raise ValueError("invalid collection page file list")
        for path in paths:
            yield read_page(path)["raw_response"]
        return
    pages = module_archive.get("pages", []) if isinstance(module_archive, dict) else module_archive
    if not isinstance(pages, list) or len(pages) > 100_000:
        raise ValueError("invalid legacy page list")
    for raw_page in pages:
        if isinstance(raw_page, str):
            if len(raw_page) > 16_000_000:
                raise ValueError("legacy page exceeds size limit")
            try:
                records = json.loads(raw_page)
            except (ValueError, RecursionError) as exc:
                raise ValueError("invalid legacy page JSON") from exc
        else:
            records = raw_page
        if not isinstance(records, list) or len(records) > 100_000 or any(not isinstance(item, dict) for item in records):
            raise ValueError("invalid legacy page records")
        yield records


def _scope_dir(repository_id: int, module: str, fingerprint: str) -> Path:
    if type(repository_id) is not int or repository_id <= 0 or module not in MODULES or not FINGERPRINT.fullmatch(fingerprint):
        raise ValueError("invalid collection scope")
    path = (COLLECTED_ROOT / str(repository_id) / module / fingerprint).resolve()
    if not path.is_relative_to(COLLECTED_ROOT):
        raise ValueError("collection scope escapes data root")
    return path


def _stored_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)
