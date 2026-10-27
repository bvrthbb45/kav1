"""Load users and items into the server database.

Usage:
    python seed.py --excel data.xlsx
    python seed.py --users users.csv --items items.csv
    python seed.py --demo

The Excel file can hold sheets for item types, soldiers and items (download
the template from the control panel); columns are matched by their titles.

CSV files are UTF-8 (Excel "CSV UTF-8" is fine) with a header row:
    users.csv: user_id,full_name,unit
    items.csv: qr_id,name,category
Existing rows with the same id are updated; item status is never reset.
"""

import argparse
import csv
import sys

from app import catalog, excel, schemas, services
from app.database import SessionLocal, init_db

DEMO_USERS = [
    schemas.UserIn(user_id="1000001", full_name="ישראל ישראלי", unit="פלוגה א"),
    schemas.UserIn(user_id="1000002", full_name="דנה כהן", unit="פלוגה ב"),
    schemas.UserIn(user_id="1000003", full_name="יוסי לוי", unit="מפקדה"),
]
DEMO_ITEMS = [
    schemas.ItemIn(qr_id="ITEM-0001", name="מכשיר קשר", category="מכשיר קשר"),
    schemas.ItemIn(qr_id="ITEM-0002", name="משקפת", category="משקפת"),
    schemas.ItemIn(qr_id="ITEM-0003", name="פנס ראש", category="פנס ראש"),
]


def _read_csv(path, model):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [
            model(**{k.strip(): v.strip() for k, v in row.items()})
            for row in csv.DictReader(f)
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--users", help="CSV file with users")
    parser.add_argument("--items", help="CSV file with items")
    parser.add_argument(
        "--excel", help="Excel (xlsx) or CSV file in the import template layout"
    )
    parser.add_argument("--demo", action="store_true", help="load demo data")
    args = parser.parse_args()

    if args.excel:
        init_db()
        with open(args.excel, "rb") as f, SessionLocal() as db:
            try:
                result = excel.import_file(db, f.read(), args.excel)
            except catalog.CatalogError as e:
                print(e)
                return 1
        print(result["message"])
        for line in result["errors"]:
            print(" -", line)
        return 0

    users, items = [], []
    if args.demo:
        users += DEMO_USERS
        items += DEMO_ITEMS
    if args.users:
        users += _read_csv(args.users, schemas.UserIn)
    if args.items:
        items += _read_csv(args.items, schemas.ItemIn)
    if not users and not items:
        parser.print_help()
        return 1

    init_db()
    with SessionLocal() as db:
        print(f"משתמשים שנשמרו: {services.upsert_users(db, users)}")
        print(f"פריטים שנשמרו: {services.upsert_items(db, items)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
