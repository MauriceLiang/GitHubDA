from datetime import UTC, date, datetime


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return utc_naive(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def day_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)
