#!/usr/bin/env bash
# Builds a small update (patch) zip for an existing Windows install: program
# files only, no Python, no database. update.bat inside backs up the
# database and the old program files, then copies the new files over
# (nothing is deleted). Database tables/columns are added by the server on
# start-up; existing data is kept.
#
# Usage: server/packaging/build_update_zip.sh [output_dir]
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_DIR="$(cd "$SERVER_DIR/.." && pwd)"
OUT_DIR="$(mkdir -p "${1:-$SERVER_DIR/dist}" && cd "${1:-$SERVER_DIR/dist}" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
PKG="$WORK/OlympusUpdate"
PATCH="$PKG/patch"
mkdir -p "$PATCH"

cp -r "$SERVER_DIR/app" "$SERVER_DIR/main.py" "$SERVER_DIR/seed.py" \
      "$SERVER_DIR/requirements.txt" "$PATCH/"
find "$PATCH/app" -name '__pycache__' -prune -exec rm -rf {} +
# Scripts and docs; data\ (templates, your Excel files) is left alone.
cp -r "$SERVER_DIR/packaging/windows/." "$PATCH/"
rm -rf "$PATCH/data"

VERSION="$(git -C "$REPO_DIR" log -1 --format='%h %cd' --date=format:'%Y-%m-%d %H:%M')"
printf 'Olympus server version: %s\n' "$VERSION" > "$PATCH/VERSION.txt"

cp "$SERVER_DIR/packaging/update/update.bat" "$PKG/"
cat > "$PKG/README_UPDATE_HE.txt" <<'EOF'
עדכון שרת אולימפוס (פאצ')
=========================
העדכון מחליף רק קבצי תוכנה. מסד הנתונים (warehouse.db), הגיבויים, היומנים
וקבצי האקסל שלך לא נמחקים ולא משתנים.

1. חלץ את כל הקובץ לתיקייה כלשהי (למשל שולחן העבודה).
2. לחץ פעמיים על update.bat ואשר הרשאת מנהל.
3. הסקריפט מוצא לבד את תיקיית השרת המותקן. אם הוא לא מוצא, הוא מבקש להקליד אותה
   (התיקייה שיש בה start_server.bat ו-warehouse.db).
4. לפני ההחלפה נשמרים בתיקייה backups:
   - עותק של מסד הנתונים: warehouse_before_update_<תאריך>.db
   - עותק של קבצי התוכנה הקודמים: program_before_update_<תאריך>
5. אם השרת המעודכן לא עולה, הקבצים הקודמים מוחזרים אוטומטית.
EOF
for f in "$PKG"/*.bat "$PKG"/*.txt "$PATCH"/*.bat "$PATCH"/*.txt; do
    sed -i 's/\r$//; s/$/\r/' "$f"
done

ZIP="$OUT_DIR/Olympus-Server-Update.zip"
rm -f "$ZIP"
(cd "$WORK" && zip -qr9 "$ZIP" OlympusUpdate)
echo "Created $ZIP ($(du -h "$ZIP" | cut -f1)) - $VERSION"
