#!/usr/bin/env python3
"""Kav1 - read-only report of the visitor property keys in a database (standalone, stdlib only).

  python db_keys_report.py <local_database.db>

Writes kav1_keys_report.html (UTF-8, so Hebrew is readable) next to the database and opens it in the
browser. The database is opened read-only and is never changed.

It answers: which keys exist, how many visitors have each, which of them hold dates (and in what
format), and - the point of this tool - how many visitors the lists can show a project, an approval
expiry and a classification (SAV"T) expiry for, with the key names the system reads.
No personal data is shown: only key names, counts, formats like 99.99.9999, and the values of keys that
have very few different values (statuses such as yes/no).
"""

import collections
import html
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_KEYS = ("פרויקט", "פרויקטים", "project", "projects")
APPROVAL_KEYS = ("תוקף אישור", "תאריך תום אישור")  # in this order of preference
CLASSIFICATION_KEYS = ('תוקף סב"ט', "תוקף סב״ט", "תוקף סיווג", "תוקף סיווג בטחוני")
INFOSEC_KEYS = ("אבטחת מידע",)
OPTIONS = ("מאושר", "מאושר חריג על ידי מפקד היחידה", "לא מאושר")

_DATE = re.compile(r"(\d{1,2})\s*[./\-]?\s*(\d{1,2})\s*[./\-]?\s*(\d{4}|\d{2})")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RANGE = re.compile(r"\s+[-–—]\s+|\s+עד\s+")


def parse_date(value):
    """Same rules as the server (visitor_extras.parse_date)."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    parts = [p for p in _RANGE.split(text) if p.strip()]
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
        if not 2000 <= year <= 2100:
            return None
        return date(year, month, day)
    except ValueError:
        return None


def pattern(text):
    return re.sub(r"[א-תa-zA-Z]", "a", re.sub(r"\d", "9", text))[:26]


def find_value(props, names):
    """First non-empty value, trying the names in order of preference."""
    lowered = {str(k).strip().lower(): v for k, v in props.items()}
    for n in names:
        v = lowered.get(n.strip().lower())
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def main():
    if len(sys.argv) < 2:
        print("Drag local_database.db into this window, then Enter.")
        src = input("> ").strip().strip('"').strip("'")
    else:
        src = sys.argv[1].strip().strip('"')
    db = Path(src).expanduser().resolve()
    if not db.is_file():
        sys.exit("File not found: %s" % db)
    conn = sqlite3.connect("file:%s?mode=ro" % db.as_posix(), uri=True)
    values = collections.defaultdict(list)
    total = 0
    cover = collections.Counter()
    infosec = collections.Counter()
    today = date.today()
    for (raw,) in conn.execute("SELECT properties FROM visitors"):
        total += 1
        try:
            props = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        except ValueError:
            props = {}
        if not isinstance(props, dict):
            props = {}
        for k, v in props.items():
            values[str(k)].append("" if v is None else str(v).strip())
        if find_value(props, PROJECT_KEYS):
            cover["project"] += 1
        for label, names in (
            ("approval", APPROVAL_KEYS),
            ("classification", CLASSIFICATION_KEYS),
        ):
            v = find_value(props, names)
            if v is None:
                continue
            d = parse_date(v)
            cover[label + "_present"] += 1
            if d is None:
                cover[label + "_unreadable"] += 1
            else:
                cover[label + "_readable"] += 1
                if d < today:
                    cover[label + "_expired"] += 1
        s = find_value(props, INFOSEC_KEYS)
        infosec["(empty)" if s is None else (s if s in OPTIONS else "old value")] += 1
    conn.close()

    rows = []
    for key, vs in sorted(values.items(), key=lambda kv: -len(kv[1])):
        non_empty = [x for x in vs if x]
        dates = sum(1 for x in non_empty if parse_date(x))
        distinct = collections.Counter(non_empty)
        if len(distinct) <= 10 and all(len(x) <= 30 for x in distinct):
            sample = "; ".join("%s (%d)" % (x, n) for x, n in distinct.most_common())
        else:
            sample = "formats: " + ", ".join(
                "%s (%d)" % (p, n)
                for p, n in collections.Counter(
                    pattern(x) for x in non_empty
                ).most_common(4)
            )
        role = ""
        if key.strip().lower() in {n.lower() for n in PROJECT_KEYS}:
            role = "project"
        elif key.strip().lower() in {n.lower() for n in APPROVAL_KEYS}:
            role = "approval expiry (read)"
        elif key.strip().lower() in {n.lower() for n in CLASSIFICATION_KEYS}:
            role = "classification expiry (read)"
        elif key.strip() in INFOSEC_KEYS:
            role = "information security status (read)"
        rows.append((key, len(vs), dates, role, sample))

    def pct(n):
        return "%d (%.0f%%)" % (n, 100.0 * n / total) if total else "0"

    out = db.with_name("kav1_keys_report.html")
    body = [
        "<h1>Kav1 - visitor keys report</h1>",
        "<p>%s &nbsp;|&nbsp; visitors: <b>%d</b></p>" % (html.escape(str(db)), total),
    ]
    body.append(
        "<h2>What the lists can show now</h2><table><tr><th></th><th>visitors</th></tr>"
    )
    body.append("<tr><td>have a project</td><td>%s</td></tr>" % pct(cover["project"]))
    for label, name in (
        ("approval", "approval expiry"),
        ("classification", "classification (SAV&quot;T) expiry"),
    ):
        body.append(
            "<tr><td>%s: has a value</td><td>%s</td></tr>"
            % (name, pct(cover[label + "_present"]))
        )
        body.append(
            "<tr><td>&nbsp;&nbsp;readable date</td><td>%s</td></tr>"
            % pct(cover[label + "_readable"])
        )
        body.append(
            "<tr><td>&nbsp;&nbsp;text that is not a date</td><td>%s</td></tr>"
            % pct(cover[label + "_unreadable"])
        )
        body.append(
            "<tr><td>&nbsp;&nbsp;already expired</td><td>%s</td></tr>"
            % pct(cover[label + "_expired"])
        )
    body.append("</table>")
    body.append(
        "<h2>Information-security status</h2><p>"
        + ", ".join("%s: %d" % (html.escape(k), n) for k, n in infosec.most_common())
        + "</p>"
    )
    body.append(
        "<h2>All keys</h2><table><tr><th>key</th><th>visitors</th><th>look like dates</th><th>read by the system as</th><th>values / formats</th></tr>"
    )
    for key, n, dates, role, sample in rows:
        body.append(
            "<tr><td>%s</td><td>%d</td><td>%d</td><td>%s</td><td>%s</td></tr>"
            % (html.escape(key), n, dates, role, html.escape(sample))
        )
    body.append(
        "</table><p>Keys that look like dates but are not read by the system yet are the candidates to add.</p>"
    )
    out.write_text(
        "<!doctype html><meta charset='utf-8'><title>Kav1 keys</title><style>body{font-family:Segoe UI,Arial;margin:24px;direction:rtl}"
        "table{border-collapse:collapse;margin-bottom:20px}td,th{border:1px solid #bbb;padding:5px 10px;text-align:right;font-size:14px}th{background:#eee}"
        "h1{font-size:22px}h2{font-size:17px;margin-top:22px}</style>" + "".join(body),
        encoding="utf-8",
    )
    print("Report written: %s" % out)
    try:
        os.startfile(str(out))  # type: ignore[attr-defined]
    except AttributeError:
        print("(open it in a browser)")
    if sys.stdin.isatty():
        input("\nPress Enter to close ...")


if __name__ == "__main__":
    main()
