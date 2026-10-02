"""Excel import (soldiers, items, item types) and Excel reports."""

import csv
import io
import re
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import catalog, messages, models, schemas, services

STATUS_LABELS = {
    models.STATUS_AVAILABLE: "זמין",
    models.STATUS_BORROWED: "מושאל",
    models.STATUS_ISSUED: "מנופק",
}
ACTION_LABELS = {
    models.ACTION_BORROW: "השאלה",
    models.ACTION_ISSUE: "ניפוק",
    models.ACTION_RETURN: "החזרה",
}
MAX_REPORTED_ERRORS = 30

# --- Import ------------------------------------------------------------------

# Accepted column titles (compared after _normalize).
SERIAL = {
    "מספרסידורי",
    "סידורי",
    "מסד",
    "סריאלי",
    "סיריאלי",
    "מספרצ",
    "צ",
    "serial",
    "qr",
    "qrid",
    "ברקוד",
}
ITEM_NAME = {"שםפריט", "פריט", "תיאור", "תיאורפריט", "itemname", "name", "שם"}
CATEGORY = {"סוגפריט", "סוג", "קטגוריה", "category", "type"}
TARGET = {"כמותבתקן", "תקן", "כמות", "target", "targetqty"}
USER_ID = {"מספראישי", "מא", "מסאישי", "אישי", "userid", "id", "תז"}
FULL_NAME = {"שםמלא", "שם", "fullname", "name"}
UNIT = {"יחידה", "פלוגה", "מחלקה", "unit"}


def _normalize(title) -> str:
    return re.sub(r"[\s\"'׳״.\-_]", "", str(title or "")).lower()


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _find(header: Sequence[str], names: set) -> Optional[int]:
    for index, title in enumerate(header):
        if title in names:
            return index
    return None


def _sheets(data: bytes, filename: str) -> List[tuple]:
    """[(sheet name, rows)] from an xlsx or csv upload."""
    if data[:2] == b"PK":
        try:
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001 - any corrupt file
            raise catalog.CatalogError(messages.IMPORT_BAD_FILE) from e
        return [
            (ws.title, [list(r) for r in ws.iter_rows(values_only=True)])
            for ws in workbook.worksheets
        ]
    for encoding in ("utf-8-sig", "cp1255"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise catalog.CatalogError(messages.IMPORT_BAD_FILE)
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [(filename or "CSV", list(csv.reader(io.StringIO(text), dialect)))]


def import_file(db: Session, data: bytes, filename: str = "") -> Dict:
    """Load item types, soldiers and items; existing rows are updated."""
    categories: Dict[str, Optional[int]] = {}
    users: List[schemas.UserIn] = []
    items: List[schemas.ItemIn] = []
    errors: List[str] = []

    def error(sheet, row, text):
        if len(errors) < MAX_REPORTED_ERRORS:
            errors.append(
                messages.IMPORT_ROW_ERROR.format(sheet=sheet, row=row, error=text)
            )

    for sheet, rows in _sheets(data, filename):
        start = next((i for i, r in enumerate(rows) if any(_cell(c) for c in r)), None)
        if start is None:
            continue
        header = [_normalize(c) for c in rows[start]]
        serial = _find(header, SERIAL)
        user_id = _find(header, USER_ID)
        category = _find(header, CATEGORY)
        target = _find(header, TARGET)

        def value(row, index):
            return _cell(row[index]) if index is not None and index < len(row) else ""

        body = list(enumerate(rows[start + 1 :], start=start + 2))
        if serial is not None:
            name = _find(header, ITEM_NAME)
            for row_no, row in body:
                qr_id = value(row, serial)
                if not qr_id:
                    continue
                cat = value(row, category)
                item_name = value(row, name) or cat
                try:
                    items.append(
                        schemas.ItemIn(qr_id=qr_id, name=item_name, category=cat)
                    )
                except ValidationError:
                    error(sheet, row_no, "חסר שם פריט או סוג פריט")
                    continue
                if cat:
                    categories.setdefault(cat, None)
        elif user_id is not None:
            name = _find(header, FULL_NAME)
            unit = _find(header, UNIT)
            for row_no, row in body:
                uid = value(row, user_id)
                if not uid:
                    continue
                try:
                    users.append(
                        schemas.UserIn(
                            user_id=uid,
                            full_name=value(row, name),
                            unit=value(row, unit),
                        )
                    )
                except ValidationError:
                    error(sheet, row_no, "חסר שם מלא")
        elif category is not None:
            for row_no, row in body:
                cat = value(row, category)
                if not cat:
                    continue
                raw = value(row, target)
                try:
                    categories[cat] = int(float(raw)) if raw else None
                except ValueError:
                    error(sheet, row_no, f"כמות לא תקינה: {raw}")

    if not (categories or users or items):
        raise catalog.CatalogError(messages.IMPORT_NOTHING)

    existing = {c.name: c for c in db.scalars(select(models.Category))}
    for name, target_qty in categories.items():
        if name in existing:
            if target_qty is not None:
                existing[name].target_qty = target_qty
        else:
            db.add(models.Category(name=name, target_qty=target_qty))
    db.commit()
    services.upsert_users(db, users)
    services.upsert_items(db, items)
    return {
        "users": len(users),
        "items": len(items),
        "categories": len(categories),
        "errors": errors,
        "message": messages.IMPORT_DONE.format(
            users=len(users), items=len(items), categories=len(categories)
        ),
    }


# --- Export --------------------------------------------------------------------

HEADER_FILL = PatternFill("solid", fgColor="434C2F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
DATE_FORMAT = "dd/mm/yyyy hh:mm"


def _local(epoch_ms: Optional[int]) -> Optional[datetime]:
    return datetime.fromtimestamp(epoch_ms / 1000) if epoch_ms else None


def _sheet(wb: Workbook, title: str, headers: List[str], rows: Iterable[list]):
    ws = wb.create_sheet(title)
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center")
    widths = [len(h) + 2 for h in headers]
    for row in rows:
        ws.append(row)
        for i, v in enumerate(row):
            if isinstance(v, datetime):
                ws.cell(ws.max_row, i + 1).number_format = DATE_FORMAT
                widths[i] = max(widths[i], 17)
            else:
                widths[i] = max(widths[i], min(len(str(v or "")) + 2, 50))
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions
    return ws


def _inventory(wb: Workbook, db: Session) -> None:
    state = services.pull_state(db)
    users = {u.user_id: u for u in state.users}
    rows = []
    for i in sorted(state.items, key=lambda i: (i.category, i.name, i.qr_id)):
        holder = users.get(i.holder_user_id) if i.holder_user_id else None
        rows.append(
            [
                i.qr_id,
                i.name,
                i.category or messages.NO_CATEGORY,
                STATUS_LABELS.get(i.current_status, i.current_status),
                holder.full_name if holder else (i.holder_user_id or ""),
                i.holder_user_id or "",
                holder.unit if holder else "",
                _local(i.last_action_at),
            ]
        )
    _sheet(
        wb,
        "מלאי",
        [
            "מספר סידורי",
            "שם פריט",
            "סוג פריט",
            "סטטוס",
            "מחזיק",
            "מספר אישי",
            "יחידה",
            "פעולה אחרונה",
        ],
        rows,
    )


def _types(wb: Workbook, db: Session) -> None:
    _sheet(
        wb,
        "סיכום לפי סוג",
        [
            "סוג פריט",
            "כמות בתקן",
            "רשומים במערכת",
            "זמינים",
            "מושאלים",
            "מנופקים",
            "חסרים לתקן",
        ],
        (
            [
                r["label"],
                r["target_qty"],
                r["total"],
                r["available"],
                r["borrowed"],
                r["issued"],
                r["missing"],
            ]
            for r in catalog.category_summary(db)
        ),
    )


def _holders(
    wb: Workbook, db: Session, user_id: Optional[str] = None, title="ציוד אצל חיילים"
) -> None:
    _sheet(
        wb,
        title,
        [
            "שם",
            "מספר אישי",
            "יחידה",
            "שם פריט",
            "סוג פריט",
            "מספר סידורי",
            "סטטוס",
            "מתאריך",
        ],
        (
            [
                r["user_name"],
                r["user_id"],
                r["unit"],
                r["item_name"],
                r["category"],
                r["qr_id"],
                STATUS_LABELS.get(r["status"], r["status"]),
                _local(r["since"]),
            ]
            for r in catalog.holdings(db, user_id)
        ),
    )


def _history(wb: Workbook, rows: List[Dict], title: str) -> None:
    _sheet(
        wb,
        title,
        [
            "תאריך",
            "פעולה",
            "שם פריט",
            "סוג פריט",
            "מספר סידורי",
            "חייל",
            "מספר אישי",
            "יחידה",
        ],
        (
            [
                _local(r["timestamp"]),
                ACTION_LABELS.get(r["action_type"], r["action_type"]),
                r["item_name"],
                r["category"],
                r["qr_id"],
                r["user_name"],
                r["user_id"],
                r["unit"],
            ]
            for r in rows
        ),
    )


def _users(wb: Workbook, db: Session) -> None:
    held = {}
    for r in catalog.holdings(db):
        held[r["user_id"]] = held.get(r["user_id"], 0) + 1
    _sheet(
        wb,
        "חיילים",
        ["מספר אישי", "שם מלא", "יחידה", "פריטים אצלו"],
        (
            [u.user_id, u.full_name, u.unit, held.get(u.user_id, 0)]
            for u in db.scalars(select(models.User).order_by(models.User.full_name))
        ),
    )


def _finish(wb: Workbook) -> bytes:
    del wb[wb.sheetnames[0]]  # the empty default sheet
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _new() -> Workbook:
    return Workbook()


REPORTS: Dict[str, str] = {
    "full": "דוח מלא",
    "inventory": "מלאי",
    "types": "סיכום לפי סוג",
    "holders": "ציוד אצל חיילים",
    "transactions": "יומן פעולות",
    "users": "חיילים",
}


def export_report(
    db: Session,
    report: str,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> bytes:
    wb = _new()
    builders: Dict[str, Callable[[], None]] = {
        "inventory": lambda: _inventory(wb, db),
        "types": lambda: _types(wb, db),
        "holders": lambda: _holders(wb, db),
        "transactions": lambda: _history(
            wb, catalog.transactions(db, start_ms, end_ms), "יומן פעולות"
        ),
        "users": lambda: _users(wb, db),
    }
    if report == "full":
        for name in ("types", "inventory", "holders", "users", "transactions"):
            builders[name]()
    else:
        builders[report]()
    return _finish(wb)


def export_user_card(db: Session, user_id: str) -> bytes:
    card = catalog.user_card(db, user_id)
    wb = _new()
    u = card["user"]
    ws = wb.create_sheet("פרטי חייל")
    ws.sheet_view.rightToLeft = True
    for label, val in (
        ("שם מלא", u["full_name"]),
        ("מספר אישי", u["user_id"]),
        ("יחידה", u["unit"]),
        ("פריטים אצלו", len(card["holding"])),
        ("תאריך הפקה", datetime.now()),
    ):
        ws.append([label, val])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        if isinstance(val, datetime):
            ws.cell(ws.max_row, 2).number_format = DATE_FORMAT
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 30
    _holders(wb, db, user_id, title="ציוד אצלו")
    _history(wb, card["history"], "היסטוריה")
    return _finish(wb)


def template() -> bytes:
    """Empty import file with the expected columns and one example row each."""
    wb = _new()
    _sheet(
        wb, "סוגי פריטים", ["סוג פריט", "כמות בתקן"], [["מכשיר קשר", 50], ["משקפת", 20]]
    )
    _sheet(
        wb,
        "חיילים",
        ["מספר אישי", "שם מלא", "יחידה"],
        [["1234567", "ישראל ישראלי", "פלוגה א"]],
    )
    _sheet(
        wb,
        "מלאי",
        ["מספר סידורי", "שם פריט", "סוג פריט"],
        [["MK-0001", "מכשיר קשר 710", "מכשיר קשר"], ["BN-0001", "משקפת 7x50", "משקפת"]],
    )
    return _finish(wb)
