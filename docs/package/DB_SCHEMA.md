# מבנה מסד הנתונים (local_database.db)

נוצר אוטומטית מהמודלים של השרת. SQLite, קובץ אחד. הטבלאות מוגדרות ב-`models.py` וב-`routes_locations.py`.

## `audit_logs`

יומן פעולות מנהל (כולל שינוי מתגי פיצ'רים, מפות ופול מלווים).

```sql
CREATE TABLE audit_logs (
	id INTEGER NOT NULL, 
	user_id INTEGER, 
	username VARCHAR NOT NULL, 
	action VARCHAR NOT NULL, 
	detail VARCHAR, 
	timestamp DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)
CREATE INDEX ix_audit_logs_id ON audit_logs (id)
CREATE INDEX ix_audit_logs_timestamp ON audit_logs (timestamp)
```

## `permissions`

קטלוג ההרשאות. נטען מ-`permissions_catalog.py` בכל הפעלה, ולעולם לא נמחק.

```sql
CREATE TABLE permissions (
	"key" VARCHAR NOT NULL, 
	label VARCHAR NOT NULL, 
	"group" VARCHAR NOT NULL, 
	PRIMARY KEY ("key")
)
CREATE INDEX ix_permissions_key ON permissions ("key")
```

## `role_permissions`

אילו הרשאות מוחזקות בידי כל תפקיד. זו הטבלה שהתרוקנה בבאג.

```sql
CREATE TABLE role_permissions (
	role_id INTEGER NOT NULL, 
	permission_key VARCHAR NOT NULL, 
	PRIMARY KEY (role_id, permission_key), 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
	FOREIGN KEY(permission_key) REFERENCES permissions ("key") ON DELETE CASCADE
)
```

## `roles`

תפקידים. התפקיד המוגן (מנהל) לא ניתן למחיקה.

```sql
CREATE TABLE roles (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	description VARCHAR, 
	is_protected BOOLEAN NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id)
)
CREATE INDEX ix_roles_id ON roles (id)
CREATE UNIQUE INDEX ix_roles_name ON roles (name)
```

## `sessions`

הפעלות התחברות (נשמר hash של האסימון).

```sql
CREATE TABLE sessions (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	token_hash VARCHAR NOT NULL, 
	expires_at DATETIME NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)
CREATE INDEX ix_sessions_id ON sessions (id)
CREATE UNIQUE INDEX ix_sessions_token_hash ON sessions (token_hash)
CREATE INDEX ix_sessions_user_id ON sessions (user_id)
```

## `settings`

הגדרות מערכת (JSON).

```sql
CREATE TABLE settings (
	"key" VARCHAR NOT NULL, 
	value VARCHAR, 
	updated_at DATETIME, 
	PRIMARY KEY ("key")
)
CREATE INDEX ix_settings_key ON settings ("key")
```

## `users`

משתמשי המערכת (לא מבקרים). סיסמאות נשמרות כ-hash.

```sql
CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	full_name VARCHAR, 
	role_id INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	must_change_password BOOLEAN NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(role_id) REFERENCES roles (id)
)
CREATE INDEX ix_users_id ON users (id)
CREATE UNIQUE INDEX ix_users_username ON users (username)
```

## `visitor_logs`

יומן כניסות/יציאות/יצירה/עדכון לכל מבקר. נוסף עליו אינדקס (visitor_dbid, timestamp) ו-(timestamp) שמונעים איטיות.

```sql
CREATE TABLE visitor_logs (
	id INTEGER NOT NULL, 
	visitor_dbid INTEGER NOT NULL, 
	action VARCHAR NOT NULL, 
	timestamp DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(visitor_dbid) REFERENCES visitors (dbid) ON DELETE CASCADE
)
CREATE INDEX ix_visitor_logs_id ON visitor_logs (id)
CREATE INDEX ix_visitor_logs_timestamp ON visitor_logs (timestamp)
CREATE INDEX ix_visitor_logs_visitor_dbid_timestamp ON visitor_logs (visitor_dbid, timestamp)
```

## `visitors`

המבקרים (הקבלנים). `properties` הוא JSON חופשי: כאן נשמרים פרויקט, אבטחת מידע, תוקפים ושאר הקטגוריות. **לעולם לא נמחק על ידי עדכון או הפעלה.**

```sql
CREATE TABLE visitors (
	dbid INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	visitorid VARCHAR NOT NULL, 
	inside BOOLEAN NOT NULL, 
	properties JSON, 
	PRIMARY KEY (dbid)
)
CREATE INDEX ix_visitors_dbid ON visitors (dbid)
CREATE INDEX ix_visitors_name ON visitors (name)
CREATE UNIQUE INDEX ix_visitors_visitorid ON visitors (visitorid)
```

## מפתחות מוכרים ב-`visitors.properties`

| מפתח | משמעות | הערות |
|---|---|---|
| `פרויקט` | הפרויקט של המבקר | גם `פרויקטים`, `project` |
| `אבטחת מידע` | סטטוס האישור: `מאושר` / `מאושר חריג על ידי מפקד היחידה` / `לא מאושר` | ערכים ישנים נשמרים כפי שהם |
| `תוקף אישור` | תוקף האישור | גם `תאריך תום אישור` (בסדר העדיפות הזה, ואם יש ערך בראשון הוא מוצג). חובה כשיש אישור (רק כשהמתג "חובה לבחור אבטחת מידע" פועל) |
| `תוקף סב"ט` | תוקף הסב"ט | אופציונלי. גם `תוקף סב״ט`, `תוקף סיווג` |

תאריכים נקראים בכל פורמט נפוץ (`31.12.2026`, `31/12/26`, `2026-12-31`, טווח: התאריך האחרון). תאריך שלא ניתן לקרוא נשאר כפי שהוקלד ומוצג כטקסט.

## הרשאות "שליטה ומיקומים"

| הרשאה | מה מאפשרת |
|---|---|
| `locations.manage` (ניהול פאנל) | הכל: העלאה, שינוי שם ומחיקה של מפות, בנוסף להפעלה |
| `locations.operate` (הפעלה) | הצבת נקודות על המפה, שיוך מלווים להצבות, וניהול פול המלווים |

כל אחת מהן מספיקה כדי לפתוח את הדף. ההרשאות מופיעות בעורך התפקידים. מתג ההפעלה של הפיצ'ר עצמו דורש `admin.settings`.
