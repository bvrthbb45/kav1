"""Printable QR labels (A4 sheet), rendered on the server so no internet is needed."""

import html
import io
from typing import List

import qrcode
import qrcode.image.svg

from . import models

PAGE = """<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><title>מדבקות QR</title>
<style>
  @page {{ size: A4; margin: 8mm; }}
  body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0; }}
  .bar {{ padding: 10px 16px; background: #434c2f; color: #fff; display: flex; gap: 12px; align-items: center; }}
  .bar button {{ font: inherit; padding: 6px 16px; border-radius: 6px; border: 0; cursor: pointer; }}
  .sheet {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 4mm; padding: 6mm; }}
  .label {{ border: 1px dashed #999; border-radius: 2mm; padding: 2mm; text-align: center; break-inside: avoid; }}
  .label svg {{ width: 30mm; height: 30mm; display: block; margin: 0 auto; }}
  .serial {{ font: bold 11pt monospace; direction: ltr; }}
  .name {{ font-size: 9pt; }}
  .type {{ font-size: 8pt; color: #555; }}
  @media print {{ .bar {{ display: none; }} .label {{ border-color: #ccc; }} }}
</style></head><body>
<div class="bar"><b>{count} מדבקות</b><button onclick="print()">הדפסה</button>
<span>מומלץ להדפיס על דף מדבקות A4 (4 עמודות), בקנה מידה 100%</span></div>
<div class="sheet">{labels}</div>
</body></html>"""


def qr_svg(text: str) -> str:
    image = qrcode.make(
        text,
        image_factory=qrcode.image.svg.SvgPathImage,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        border=1,
    )
    out = io.BytesIO()
    image.save(out)
    svg = out.getvalue().decode("utf-8")
    return svg[svg.index("<svg") :]  # drop the XML declaration for inline use


def render(items: List[models.Item]) -> str:
    labels = "".join(
        '<div class="label">{svg}<div class="serial">{serial}</div>'
        '<div class="name">{name}</div><div class="type">{type}</div></div>'.format(
            svg=qr_svg(item.qr_id),
            serial=html.escape(item.qr_id),
            name=html.escape(item.name),
            type=html.escape(item.category or ""),
        )
        for item in items
    )
    return PAGE.format(count=len(items), labels=labels)


def count_page(warehouse: str, rows) -> str:
    """Printable stock-count sheet for one warehouse, shelf by shelf."""
    from html import escape
    from datetime import datetime

    body = (
        "".join(
            "<tr><td>{shelf}</td><td><b>{name}</b></td><td class='ltr'>{qr}</td>"
            "<td>{cat}</td><td class='num'>{qty}</td><td class='box'></td><td class='box'></td></tr>".format(
                shelf=escape(r["shelf"] or "—"),
                name=escape(r["name"]),
                qr=escape(r["qr_id"]),
                cat=escape(r["category"] or "—"),
                qty=r["quantity"],
            )
            for r in rows
        )
        or "<tr><td colspan='7'>אין פריטים במחסן</td></tr>"
    )
    return f"""<!doctype html><html dir="rtl" lang="he"><head><meta charset="utf-8">
<title>ספירת מלאי – {escape(warehouse)}</title><style>
body{{font-family:Arial,sans-serif;margin:24px;color:#111}}
h1{{font-size:22px;margin:0 0 4px}} .meta{{color:#555;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{border:1px solid #999;padding:6px 8px;text-align:right}}
th{{background:#434C2F;color:#fff}} .num{{text-align:center;font-weight:bold}}
.box{{width:90px}} .ltr{{direction:ltr;text-align:right}}
.sign{{margin-top:28px;display:flex;gap:60px}}
@media print{{button{{display:none}} th{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body>
<button onclick="print()">הדפסה</button>
<h1>ספירת מלאי – {escape(warehouse)}</h1>
<div class="meta">הודפס: {datetime.now().strftime("%d/%m/%Y %H:%M")} · {len(rows)} פריטים</div>
<table><thead><tr><th>מדף</th><th>פריט</th><th>מספר סידורי</th><th>סוג</th><th>כמות במערכת</th><th>נספר</th><th>הערה</th></tr></thead>
<tbody>{body}</tbody></table>
<div class="sign"><div>שם הסופר: ____________</div><div>חתימה: ____________</div></div>
<script>setTimeout(function(){{print()}},400)</script>
</body></html>"""
