"""All user-facing server messages (Hebrew)."""

PUSH_ALL_OK = "כל הפעולות סונכרנו בהצלחה ({count})"
PUSH_PARTIAL = "סונכרנו {accepted} פעולות, {rejected} נדחו"
PUSH_EMPTY = "אין פעולות לסנכרון"
PUSH_DB_ERROR = "שגיאה בשמירת הנתונים בשרת, אף פעולה לא נשמרה. נסה שוב"
PULL_OK = "הנתונים נטענו בהצלחה"

TX_ACCEPTED = "הפעולה נקלטה"
TX_DUPLICATE = "הפעולה כבר נקלטה בעבר"
TX_UNKNOWN_ITEM = "פריט לא קיים במערכת: {qr_id}"
TX_UNKNOWN_USER = "משתמש לא קיים במערכת: {user_id}"
TX_UNKNOWN_ACTION = "סוג פעולה לא חוקי: {action_type}"

UPSERT_OK = "נשמרו {count} רשומות"

VALIDATION_ERROR = "הבקשה שנשלחה אינה תקינה"
NOT_FOUND = "הכתובת המבוקשת לא נמצאה"
METHOD_NOT_ALLOWED = "שיטת הבקשה אינה נתמכת"
INTERNAL_ERROR = "שגיאה פנימית בשרת"
REQUEST_FAILED = "הבקשה נכשלה"
HEALTH_OK = "השרת פעיל"
ROOT_OK = "שרת סנכרון המחסן פעיל ומחכה לחיבור מהטאבלטים"
