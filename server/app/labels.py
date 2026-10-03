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
