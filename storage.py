"""Price history in a SQLite file.

Each launch is a "run". We save every book's price for that run,
so comparing two runs shows what got cheaper, pricier, new or gone.

A run also remembers its *scope*: either the whole shop (full run) or
only some categories (quick partial run with --categories N). The scope
decides what we are allowed to conclude when comparing two runs.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from scraper import Book

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    scope      TEXT            -- NULL = whole shop, else JSON list of categories
);
CREATE TABLE IF NOT EXISTS prices (
    run_id   INTEGER NOT NULL REFERENCES runs(id),
    url      TEXT NOT NULL,
    title    TEXT NOT NULL,
    category TEXT NOT NULL,
    price    REAL NOT NULL,
    rating   INTEGER NOT NULL,
    in_stock INTEGER NOT NULL,
    PRIMARY KEY (run_id, url)
);
"""


@dataclass
class Run:
    id: int
    scope: set[str] | None  # None = whole shop

    def covers(self, category: str) -> bool:
        return self.scope is None or category in self.scope


@dataclass
class PriceChange:
    title: str
    category: str
    url: str
    old_price: float
    new_price: float

    @property
    def diff(self) -> float:
        return round(self.new_price - self.old_price, 2)

    @property
    def diff_percent(self) -> float:
        return self.diff / self.old_price if self.old_price else 0.0


@dataclass
class Comparison:
    changed: list[PriceChange]
    new: list[Book]
    removed: list[Book]
    has_previous: bool


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
    if "scope" not in columns:  # history file created by an older version
        conn.execute("ALTER TABLE runs ADD COLUMN scope TEXT")
    return conn


def save_run(conn: sqlite3.Connection, books: list[Book], scope: list[str] | None) -> Run:
    started = datetime.now().isoformat(timespec="seconds")
    scope_json = json.dumps(scope, ensure_ascii=False) if scope is not None else None
    run_id = conn.execute("INSERT INTO runs (started_at, scope) VALUES (?, ?)",
                          (started, scope_json)).lastrowid
    conn.executemany(
        "INSERT OR REPLACE INTO prices VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(run_id, b.url, b.title, b.category, b.price, b.rating, int(b.in_stock)) for b in books],
    )
    conn.commit()
    return Run(run_id, set(scope) if scope is not None else None)


def load_run(conn: sqlite3.Connection, run: Run) -> dict[str, Book]:
    rows = conn.execute(
        "SELECT url, title, category, price, rating, in_stock FROM prices WHERE run_id = ?",
        (run.id,),
    )
    return {r[0]: Book(r[0], r[1], r[2], r[3], r[4], bool(r[5])) for r in rows}


def previous_run(conn: sqlite3.Connection, full: bool) -> Run | None:
    """The run to compare a new one with (call BEFORE saving the new run).

    A full run is compared with the last *full* run, so quick test runs
    in between don't spoil daily tracking. A partial run is compared with
    the latest run of any kind.
    """
    query = "SELECT id, scope FROM runs {} ORDER BY id DESC LIMIT 1"
    row = None
    if full:
        row = conn.execute(query.format("WHERE scope IS NULL")).fetchone()
    if row is None:
        row = conn.execute(query.format("")).fetchone()
    if row is None:
        return None
    return Run(row[0], set(json.loads(row[1])) if row[1] else None)


def compare(old: dict[str, Book], new: dict[str, Book],
            old_run: Run | None, new_run: Run) -> Comparison:
    """What changed between two runs, given what each of them actually covered.

    - "removed": was in the old run, missing now, and the new run DID check
      its category (otherwise we simply didn't look there).
    - "new": present now, absent before, and the old run DID check its
      category. A full old run checked the whole shop, so even books from a
      brand-new category count as new.
    """
    if old_run is None:
        return Comparison([], [], [], has_previous=False)

    changed = [
        PriceChange(b.title, b.category, url, old[url].price, b.price)
        for url, b in new.items()
        if url in old and old[url].price != b.price
    ]
    changed.sort(key=lambda c: c.diff_percent)  # biggest discounts first
    added = [b for url, b in new.items() if url not in old and old_run.covers(b.category)]
    removed = [b for url, b in old.items() if url not in new and new_run.covers(b.category)]
    return Comparison(changed, added, removed, has_previous=True)
