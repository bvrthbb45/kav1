"""Well-known visitor property keys (mirror of backend/app/fields.py)."""

PROJECT_KEY = "פרויקט"
PROJECT_ALIASES = ("פרויקט", "פרויקטים", "project", "projects")

CLASSIFICATION_EXPIRY_KEY = "תוקף סיווג"

INFOSEC_KEY = "אבטחת מידע"
INFOSEC_EXPIRY_KEY = "תוקף אבטחת מידע"
INFOSEC_APPROVED = "מאושר"
INFOSEC_EXCEPTION = "מאושר חריג על ידי מפקד היחידה"
INFOSEC_DENIED = "לא מאושר"
INFOSEC_OPTIONS = (INFOSEC_APPROVED, INFOSEC_EXCEPTION, INFOSEC_DENIED)

DEFAULT_WARN_DAYS = 30


def find_key(properties, aliases):
    """The actual key in `properties` matching any alias (case-insensitive)."""
    wanted = {a.strip().lower() for a in aliases}
    for key in properties or {}:
        if str(key).strip().lower() in wanted:
            return key
    return None
