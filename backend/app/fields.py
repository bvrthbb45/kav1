"""Well-known visitor (contractor) property keys and helpers.

`visitors.properties` is a free-form JSON object. A few keys have meaning for
the application; they are collected here so the names live in one place (the
client has the same constants in frontend/app/core/fields.py).

Key names match the production data: each key is looked up through a list of
aliases (case-insensitive, surrounding spaces ignored) and, when a record is
saved, written back under the key it already uses.
"""

import re
from datetime import date, datetime
from typing import Optional

PROJECT_KEY = "פרויקט"
PROJECT_ALIASES = ("פרויקט", "פרויקטים", "project", "projects")

# Validity of the security classification (סב"ט). Optional.
CLASSIFICATION_EXPIRY_KEY = 'תוקף סב"ט'
CLASSIFICATION_EXPIRY_ALIASES = (
    'תוקף סב"ט',
    "תוקף סב״ט",
    "תוקף סיווג",
    "תוקף סיווג בטחוני",
)

# Information-security status: exactly one of three values. Every approval needs
# an expiry, so the approval's validity date ("תוקף אישור") is required unless
# the status is "not approved".
INFOSEC_KEY = "אבטחת מידע"
INFOSEC_EXPIRY_KEY = "תוקף אישור"
INFOSEC_EXPIRY_ALIASES = ("תוקף אישור", "תוקף אבטחת מידע")
INFOSEC_APPROVED = "מאושר"
INFOSEC_EXCEPTION = "מאושר חריג על ידי מפקד היחידה"
INFOSEC_DENIED = "לא מאושר"
INFOSEC_OPTIONS = (INFOSEC_APPROVED, INFOSEC_EXCEPTION, INFOSEC_DENIED)

VISA_EXPIRY_KEY = "תוקף ויזה"
VISA_EXPIRY_ALIASES = ("תוקף ויזה",)

EXPIRY_GROUPS = (
    CLASSIFICATION_EXPIRY_ALIASES,
    INFOSEC_EXPIRY_ALIASES,
    VISA_EXPIRY_ALIASES,
)
DEFAULT_WARN_DAYS = 30

_DATE = re.compile(r"(\d{1,2})\s*[./\-]?\s*(\d{1,2})\s*[./\-]?\s*(\d{4}|\d{2})")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RANGE_SPLIT = re.compile(r"\s+[-–—]\s+|\s+עד\s+")


def _text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def find_key(properties, aliases) -> Optional[str]:
    """The key actually present in `properties` for any alias, else None."""
    if not properties:
        return None
    wanted = {a.strip().lower() for a in aliases}
    for key in properties:
        if str(key).strip().lower() in wanted:
            return key
    return None


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
    """Day-first dates as typed by hand in the production data.

    Accepts 2026-12-31, 01.02.2026, 01/02/26, 01-02-2026, a missing separator
    (01.012026) and ranges (01.07.2024 - 01.07.2026: the end date counts).
    Placeholders such as "0" or "-" and impossible dates give None.
    """
    text = _text(value)
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


def validate_properties(properties):
    """Validate and normalise the well-known keys of a properties dict.

    Returns a new dict. The information-security status must be one of the three
    allowed values; an approved status needs an approval expiry. Dates that can
    be read are rewritten as ISO YYYY-MM-DD under the key they already use;
    dates that cannot be read are kept as typed (old data must stay editable).
    Raises ValueError with a message meant for the operator.
    """
    if not properties:
        return properties
    result = dict(properties)

    status = get_value(result, INFOSEC_KEY)
    if status is not None and status not in INFOSEC_OPTIONS:
        raise ValueError(
            "אבטחת מידע חייב להיות אחד מהערכים: " + " / ".join(INFOSEC_OPTIONS)
        )

    for aliases in EXPIRY_GROUPS:
        key = find_key(result, aliases)
        if key is None:
            continue
        raw = _text(result[key])
        if raw is None:
            result.pop(key)
            continue
        parsed = parse_date(raw)
        if parsed is not None:
            result[key] = parsed.isoformat()

    if status in (INFOSEC_APPROVED, INFOSEC_EXCEPTION) and not get_value(
        result, INFOSEC_EXPIRY_ALIASES
    ):
        raise ValueError(f"'{INFOSEC_EXPIRY_KEY}' הוא שדה חובה כשהאישור הוא '{status}'")
    return result


def expiry_info(properties, today: date, warn_days: int = DEFAULT_WARN_DAYS):
    """Soonest readable expiry among the expiry fields.

    Returns None when the visitor has no readable expiry date, else a dict:
    field, date (ISO), days_left (negative = expired) and status
    ("expired" | "expiring" | "ok").
    """
    best = None
    for aliases in EXPIRY_GROUPS:
        key = find_key(properties, aliases)
        if key is None:
            continue
        parsed = parse_date(_text(properties[key]))
        if parsed and (best is None or parsed < best[1]):
            best = (str(key), parsed)
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
