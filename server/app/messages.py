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
TX_CONSUMABLE_ONLY_ISSUE = "הפריט {qr_id} מוגדר כניצרך – אפשר רק לנפק אותו"
TX_LOAN_ONLY_BORROW = "הפריט {qr_id} מוגדר כמושאל – אפשר רק להשאיל ולהחזיר אותו"

UPSERT_OK = "נשמרו {count} רשומות"

VALIDATION_ERROR = "הבקשה שנשלחה אינה תקינה"
NOT_FOUND = "הכתובת המבוקשת לא נמצאה"
METHOD_NOT_ALLOWED = "שיטת הבקשה אינה נתמכת"
INTERNAL_ERROR = "שגיאה פנימית בשרת"
REQUEST_FAILED = "הבקשה נכשלה"
HEALTH_OK = "השרת פעיל"
ROOT_OK = "שרת אולימפוס פעיל ומחכה לחיבור מהטאבלטים"

PANEL_LOCAL_ONLY = "פאנל הבקרה זמין רק מהמחשב של השרת"
PANEL_SYNC_REQUESTED = "סנכרון יתחיל תוך כמה שניות לכל הטאבלטים המחוברים בכבל"
PANEL_ADB_RESTARTING = "שירות ADB מאותחל, זה לוקח כמה שניות"

ITEM_SAVED = "הפריט {qr_id} נשמר"
ITEM_DELETED = "הפריט {qr_id} נמחק"
ITEM_NOT_FOUND = "הפריט {qr_id} לא קיים במערכת"
ITEM_HAS_HISTORY = "לא ניתן למחוק את הפריט {qr_id} כי יש לו היסטוריית פעולות"
USER_SAVED = "החייל {user_id} נשמר"
USER_DELETED = "החייל {user_id} נמחק"
USER_NOT_FOUND = "החייל {user_id} לא קיים במערכת"
USER_HAS_HISTORY = "לא ניתן למחוק את החייל {user_id} כי יש לו היסטוריית פעולות"
CATEGORY_SAVED = 'סוג הפריט "{name}" נשמר'
CATEGORY_DELETED = 'סוג הפריט "{name}" נמחק'
CATEGORY_IN_USE = 'לא ניתן למחוק את סוג הפריט "{name}" כי יש {count} פריטים מסוג זה'
CATEGORY_EXISTS = 'סוג הפריט "{name}" כבר קיים'
NO_CATEGORY = "ללא סוג"

IMPORT_DONE = "הייבוא הושלם: {users} חיילים, {items} פריטים, {categories} סוגי פריטים"
IMPORT_NOTHING = (
    "לא נמצאו נתונים בקובץ. ודא שהעמודות תואמות לתבנית (הורד את קובץ התבנית)"
)
IMPORT_BAD_FILE = "לא ניתן לקרוא את הקובץ. יש להעלות קובץ Excel (xlsx) או CSV"
IMPORT_ROW_ERROR = 'גיליון "{sheet}" שורה {row}: {error}'
