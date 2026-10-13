from datetime import datetime
from typing import Any

from backend.app.analytics.metrics import basic_metrics


def build_profile_metrics(profile: dict[str, Any], collected_at: datetime) -> dict[str, Any]:
    return basic_metrics(profile["stars"], profile["forks"], collected_at, profile["created_at"], profile["pushed_at"])
