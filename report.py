"""Building the Excel report (openpyxl)."""

from collections import defaultdict
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from scraper import Book
from storage import Comparison

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
GREEN = Font(color="1E7B34")
RED = Font(color="B3261E")
LINK = Font(color="0563C1", underline="single")
PRICE_FMT = "£#,##0.00"
PERCENT_FMT = "+0.0%;-0.0%;0%"


def _table(ws: Worksheet, headers: list[str], widths: list[int]) -> None:
    """Header row: colored, frozen, with filters."""
    ws.append(headers)
    for col, width in enumerate(widths, 1):
        cell = ws.cell(row=1, column=col)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A2"


def _finish(ws: Worksheet) -> None:
    ws.auto_filter.ref = ws.dimensions


def _link(ws: Worksheet, row: int, col: int, url: str) -> None:
    cell = ws.cell(row=row, column=col)
    cell.hyperlink, cell.font = url, LINK


def build_report(books: list[Book], cmp: Comparison, path: str) -> None:
    wb = Workbook()
    changes_by_url = {c.url: c for c in cmp.changed}

    # --- Sheet 1: full catalog -------------------------------------------
    ws = wb.active
    ws.title = "Catalog"
    _table(ws, ["Title", "Category", "Price", "Rating", "In stock", "Price change"],
           [60, 22, 11, 9, 10, 14])
    for b in sorted(books, key=lambda b: b.title.lower()):
        change = changes_by_url.get(b.url)
        ws.append([b.title, b.category, b.price, "★" * b.rating,
                   "yes" if b.in_stock else "no", change.diff_percent if change else None])
        row = ws.max_row
        _link(ws, row, 1, b.url)
        ws.cell(row=row, column=3).number_format = PRICE_FMT
        pct = ws.cell(row=row, column=6)
        pct.number_format = PERCENT_FMT
        if change:
            pct.font = GREEN if change.diff < 0 else RED
    _finish(ws)

    # --- Sheet 2: price changes since previous run ------------------------
    ws = wb.create_sheet("Price changes")
    _table(ws, ["Title", "Category", "Old price", "New price", "Difference", "Change"],
           [60, 22, 12, 12, 12, 10])
    for c in cmp.changed:
        ws.append([c.title, c.category, c.old_price, c.new_price, c.diff, c.diff_percent])
        row = ws.max_row
        _link(ws, row, 1, c.url)
        for col in (3, 4, 5):
            ws.cell(row=row, column=col).number_format = PRICE_FMT
        ws.cell(row=row, column=6).number_format = PERCENT_FMT
        color = GREEN if c.diff < 0 else RED
        ws.cell(row=row, column=5).font = color
        ws.cell(row=row, column=6).font = color
    if not cmp.changed:
        ws.append(["No price changes since the previous run." if cmp.has_previous
                   else "This is the first run — changes will appear after the next one."])
    _finish(ws)

    # --- Sheet 3: new / removed products ----------------------------------
    ws = wb.create_sheet("New & removed")
    _table(ws, ["Status", "Title", "Category", "Price"], [12, 60, 22, 11])
    for status, items in (("new", cmp.new), ("removed", cmp.removed)):
        for b in items:
            ws.append([status, b.title, b.category, b.price])
            _link(ws, ws.max_row, 2, b.url)
            ws.cell(row=ws.max_row, column=4).number_format = PRICE_FMT
    _finish(ws)

    # --- Sheet 4: summary by category -------------------------------------
    ws = wb.create_sheet("Summary")
    _table(ws, ["Category", "Books", "Avg price", "Min price", "Max price", "Avg rating"],
           [24, 9, 12, 12, 12, 11])
    by_cat: dict[str, list[Book]] = defaultdict(list)
    for b in books:
        by_cat[b.category].append(b)
    for name, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        prices = [b.price for b in items]
        ws.append([name, len(items), sum(prices) / len(prices), min(prices), max(prices),
                   round(sum(b.rating for b in items) / len(items), 1)])
        for col in (3, 4, 5):
            ws.cell(row=ws.max_row, column=col).number_format = PRICE_FMT
    _finish(ws)
    ws.append([])
    ws.append([f"Generated {datetime.now():%Y-%m-%d %H:%M}, {len(books)} books total"])

    wb.save(path)
