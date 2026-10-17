"""Well-known visitor (contractor) property keys and helpers.

`visitors.properties` is a free-form JSON object. A few keys have meaning for
the application; they are collected here so the names live in one place (the
client has the same constants in frontend/app/core/fields.py).
"""

from datetime import date, datetime
from typing import Optional

# Project the contractor works on. Older records may use another spelling, so
# lookups accept every alias (case-insensitive, surrounding spaces ignored);
# new records are written with PROJECT_KEY.
PROJECT_KEY = "פרויקט"
PROJECT_ALIASES = ("פרויקט", "פרויקטים", "project", "projects")

# Validity of the security classification. Optional.
CLASSIFICATION_EXPIRY_KEY = "תוקף סיווג"

# Information-security approval: exactly one of three values, plus its validity
# date. Every approval needs an expiry, so the date is required unless the
# status is "not approved".
INFOSEC_KEY = "אבטחת מידע"
INFOSEC_EXPIRY_KEY = "תוקף אבטחת מידע"
INFOSEC_APPROVED = "מאושר"
INFOSEC_EXCEPTION = "מאושר חריג על ידי מפקד היחידה"
INFOSEC_DENIED = "לא מאושר"
INFOSEC_OPTIONS = (INFOSEC_APPROVED, INFOSEC_EXCEPTION, INFOSEC_DENIED)

EXPIRY_KEYS = (CLASSIFICATION_EXPIRY_KEY, INFOSEC_EXPIRY_KEY)
DEFAULT_WARN_DAYS = 30

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y")


def _text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_value(properties, keys) -> Optional[str]:
    """First non-empty value stored under any of `keys` (aliases), as text."""
    if not properties:
        return None
    wanted = {k.strip().lower() for k in ([keys] if isinstance(keys, str) else keys)}
    for key, value in properties.items():
        if str(key).strip().lower() in wanted:
            text = _text(value)
            if text:
                return text
    return None


def get_project(properties) -> Optional[str]:
    return get_value(properties, PROJECT_ALIASES)


def parse_date(value) -> Optional[date]:
    text = _text(value)
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:  # ISO timestamp, e.g. 2026-12-31T00:00:00
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def validate_properties(properties):
    """Validate and normalise the well-known keys of a properties dict.

    Returns a new dict (dates rewritten as ISO YYYY-MM-DD, empty expiry keys
    dropped). Raises ValueError with a message meant for the operator.
    """
    if not properties:
        return properties
    result = dict(properties)

    status = get_value(result, INFOSEC_KEY)
    if status is not None and status not in INFOSEC_OPTIONS:
        raise ValueError(
            "אבטחת מידע חייב להיות אחד מהערכים: " + " / ".join(INFOSEC_OPTIONS)
        )

    for key in EXPIRY_KEYS:
        raw = get_value(result, key)
        if raw is None:
            result.pop(key, None)
            continue
        parsed = parse_date(raw)
        if parsed is None:
            raise ValueError(f"'{key}': תאריך לא תקין ({raw}). פורמט נדרש: YYYY-MM-DD")
        result[key] = parsed.isoformat()

    if status in (INFOSEC_APPROVED, INFOSEC_EXCEPTION) and not result.get(
        INFOSEC_EXPIRY_KEY
    ):
        raise ValueError(f"'{INFOSEC_EXPIRY_KEY}' הוא שדה חובה כשהאישור הוא '{status}'")
    return result


def expiry_info(properties, today: date, warn_days: int = DEFAULT_WARN_DAYS):
    """Soonest expiry among the expiry keys.

    Returns None when the visitor has no (valid) expiry date, else a dict:
    field, date (ISO), days_left (negative = expired) and status
    ("expired" | "expiring" | "ok").
    """
    best = None
    for key in EXPIRY_KEYS:
        parsed = parse_date(get_value(properties, key))
        if parsed and (best is None or parsed < best[1]):
            best = (key, parsed)
    if best is None:
        return None
    days_left = (best[1] - today).days
    if days_left < 0:
        status = "expired"
    elif days_left <= warn_days:
        status = "expiring"
    else:
        status = "ok"
    return {
        "field": best[0],
        "date": best[1].isoformat(),
        "days_left": days_left,
        "status": status,
    }


def today_local() -> date:
    return date.today()
