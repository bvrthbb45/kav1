"""Well-known visitor property keys (mirror of backend/app/fields.py)."""

import re
from datetime import date, datetime

PROJECT_KEY = "פרויקט"
PROJECT_ALIASES = ("פרויקט", "פרויקטים", "project", "projects")

CLASSIFICATION_EXPIRY_KEY = 'תוקף סב"ט'
CLASSIFICATION_EXPIRY_ALIASES = (
    'תוקף סב"ט',
    "תוקף סב״ט",
    "תוקף סיווג",
    "תוקף סיווג בטחוני",
)

INFOSEC_KEY = "אבטחת מידע"
INFOSEC_EXPIRY_KEY = "תוקף אישור"
INFOSEC_EXPIRY_ALIASES = ("תוקף אישור", "תוקף אבטחת מידע")
INFOSEC_APPROVED = "מאושר"
INFOSEC_EXCEPTION = "מאושר חריג על ידי מפקד היחידה"
INFOSEC_DENIED = "לא מאושר"
INFOSEC_OPTIONS = (INFOSEC_APPROVED, INFOSEC_EXCEPTION, INFOSEC_DENIED)

DEFAULT_WARN_DAYS = 30

_DATE = re.compile(r"(\d{1,2})\s*[./\-]?\s*(\d{1,2})\s*[./\-]?\s*(\d{4}|\d{2})")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RANGE_SPLIT = re.compile(r"\s+[-–—]\s+|\s+עד\s+")


def parse_date(value):
    """Day-first dates as typed in the production data (see backend/app/fields.py)."""
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    parts = [p for p in _RANGE_SPLIT.split(text) if p.strip()]
    text = parts[-1].strip() if parts else text
    iso = _ISO.match(text)
    try:
        if iso:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        m = _DATE.fullmatch(text)
        if not m or not re.search(r"[./\-]", text):
            return datetime.fromisoformat(text).date()
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if len(m.group(3)) == 2:
            year += 2000
        if not 2000 <= year <= 2100:  # typos such as 01.01.0226
            return None
        return date(year, month, day)
    except ValueError:
        return None


def find_key(properties, aliases):
    """The actual key in `properties` matching any alias (case-insensitive)."""
    wanted = {a.strip().lower() for a in aliases}
    for key in properties or {}:
        if str(key).strip().lower() in wanted:
            return key
    return None
