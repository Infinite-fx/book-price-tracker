"""Entry point: scrape -> save to history -> compare -> Excel report.

Usage:
    python main.py                      # whole shop (~1000 books, ~1 min)
    python main.py --categories 3       # only first 3 categories (quick test)
    python main.py --out prices.xlsx    # custom report file name
"""

import argparse
import random

import storage
from report import build_report
from scraper import scrape


def simulate_changes(conn, run_id: int, share: float = 0.05) -> None:
    """DEMO ONLY: the training site never changes its prices, so to show
    how the tracker reacts, we shift ~5% of prices in the *previous* run."""
    rows = conn.execute("SELECT url, price FROM prices WHERE run_id = ?", (run_id,)).fetchall()
    for url, price in random.sample(rows, max(1, int(len(rows) * share))):
        factor = random.choice([0.8, 0.85, 0.9, 1.1, 1.15, 1.25])
        conn.execute("UPDATE prices SET price = ? WHERE run_id = ? AND url = ?",
                     (round(price * factor, 2), run_id, url))
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Track book prices and export them to Excel.")
    parser.add_argument("--categories", type=int, help="scrape only the first N categories")
    parser.add_argument("--db", default="prices.db", help="price history file (SQLite)")
    parser.add_argument("--out", default="report.xlsx", help="Excel report file")
    parser.add_argument("--demo", action="store_true",
                        help="fake some price changes in the previous run (demo only)")
    args = parser.parse_args()

    books, checked_categories = scrape(args.categories)
    print(f"Collected {len(books)} books")
    full = args.categories is None
    scope = None if full else checked_categories

    conn = storage.connect(args.db)
    prev = storage.previous_run(conn, full)  # must be found BEFORE saving the new run
    if args.demo and prev:
        simulate_changes(conn, prev.id)
    run = storage.save_run(conn, books, scope)

    old = storage.load_run(conn, prev) if prev else {}
    new = storage.load_run(conn, run)
    cmp = storage.compare(old, new, prev, run)
    print(f"Price changes: {len(cmp.changed)}, new: {len(cmp.new)}, removed: {len(cmp.removed)}")

    build_report(books, cmp, args.out)
    print(f"Report saved to {args.out}")


if __name__ == "__main__":
    main()
