from sqlalchemy.orm import Session

from backend.app.core.clock import utc_now
from backend.app.core.config import get_settings
from backend.app.persistence.models import ApplicationSetting


GITHUB_MAX_PAGES_KEY = "github_max_pages"


def get_github_max_pages(session: Session) -> int:
    setting = session.get(ApplicationSetting, GITHUB_MAX_PAGES_KEY)
    return int(setting.setting_value) if setting else get_settings().github_max_pages


def save_github_max_pages(session: Session, value: int) -> int:
    if not 1 <= value <= 100:
        raise ValueError("github_max_pages must be between 1 and 100")
    setting = session.get(ApplicationSetting, GITHUB_MAX_PAGES_KEY)
    if setting is None:
        setting = ApplicationSetting(setting_key=GITHUB_MAX_PAGES_KEY, setting_value=str(value))
        session.add(setting)
    else:
        setting.setting_value = str(value)
        setting.updated_at = utc_now()
    session.commit()
    return value
