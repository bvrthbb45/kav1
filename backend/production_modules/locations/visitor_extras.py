# visitor_extras.py
# ---------------------------------------------------------------------------
# Additions for the visitor screens. Nothing existing is changed or removed:
#   * GET /visitors/overview : per visitor - last entry time, project, information-
#     security status and the readable expiry dates (one grouped query, no N+1).
#     The screens use it to sort "latest entry first", filter by project and show
#     expiry alerts, so the existing /visitors payload stays exactly as it was.
#   * check_properties(): server-side validation of the well-known property keys.
#     It runs ONLY while the admin switch "require information security" is on
#     (default off), so old data and old clients keep working until then.
# `visitors.properties` stays free-form JSON; the key names below match the data.
# ---------------------------------------------------------------------------

import re
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import database, models
from .dependencies import require_any_permission
from .routes_locations import (
    DEFAULT_EXPIRY_DAYS,
    FLAG_REQUIRE_INFOSEC,
    KEY_EXPIRY_DAYS,
    flag_enabled,
    get_int_setting,
)

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
INFOSEC_EXPIRY_ALIASES = ("תוקף אישור", "תוקף אבטחת מידע", "תאריך תום אישור")
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


def check_properties(db: Session, properties):
    """Validate the well-known keys when the admin switch is on; otherwise a no-op.

    Returns the properties to store (dates that can be read are rewritten as ISO)
    or raises HTTPException(400) with a message meant for the operator.
    """
    if not properties or not flag_enabled(db, FLAG_REQUIRE_INFOSEC):
        return properties
    try:
        return validate_properties(properties)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


router = APIRouter()


@router.get(
    "/visitors/overview",
    dependencies=[Depends(require_any_permission("visitor.view", "control.panel"))],
)
def visitors_overview(db: Session = Depends(database.get_db)):
    """Extra columns for the visitor lists (see the module header)."""
    warn = get_int_setting(db, KEY_EXPIRY_DAYS, DEFAULT_EXPIRY_DAYS)
    today = today_local()
    last_entry = dict(
        db.query(models.VisitorLog.visitor_dbid, func.max(models.VisitorLog.timestamp))
        .filter(models.VisitorLog.action == "entry")
        .group_by(models.VisitorLog.visitor_dbid)
        .all()
    )
    rows = []
    for dbid, props in db.query(models.Visitor.dbid, models.Visitor.properties).all():
        props = props if isinstance(props, dict) else {}
        approval = find_key(props, INFOSEC_EXPIRY_ALIASES)
        classif = find_key(props, CLASSIFICATION_EXPIRY_ALIASES)
        ts = last_entry.get(dbid)
        rows.append(
            {
                "dbid": dbid,
                "last_entry": ts.isoformat() if ts else None,
                "project": get_project(props),
                "infosec": get_value(props, INFOSEC_KEY),
                "approval": _info_one(props, approval, today, warn),
                "classification": _info_one(props, classif, today, warn),
            }
        )
    return {"warn_days": warn, "rows": rows}


def _info_one(props, key, today, warn):
    """{date, days, status, raw} for one expiry key; date is None when unreadable."""
    if key is None:
        return None
    raw = _text(props.get(key))
    if raw is None:
        return None
    parsed = parse_date(raw)
    if parsed is None:
        return {"date": None, "days": None, "status": "unreadable", "raw": raw}
    days = (parsed - today).days
    status = "expired" if days < 0 else "expiring" if days <= warn else "ok"
    return {"date": parsed.isoformat(), "days": days, "status": status, "raw": raw}
