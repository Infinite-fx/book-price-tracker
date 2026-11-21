"""Price history in a SQLite file.

Each launch is a "run". We save every book's price for that run,
so comparing two runs shows what got cheaper, pricier, new or gone.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from scraper import Book

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL
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
    return conn


def save_run(conn: sqlite3.Connection, books: list[Book]) -> int:
    started = datetime.now().isoformat(timespec="seconds")
    run_id = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (started,)).lastrowid
    conn.executemany(
        "INSERT OR REPLACE INTO prices VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(run_id, b.url, b.title, b.category, b.price, b.rating, int(b.in_stock)) for b in books],
    )
    conn.commit()
    return run_id


def load_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Book]:
    rows = conn.execute(
        "SELECT url, title, category, price, rating, in_stock FROM prices WHERE run_id = ?",
        (run_id,),
    )
    return {r[0]: Book(r[0], r[1], r[2], r[3], r[4], bool(r[5])) for r in rows}


def latest_run_id(conn: sqlite3.Connection) -> int | None:
    """Id of the most recent saved run, or None if the history is empty."""
    row = conn.execute("SELECT MAX(id) FROM runs").fetchone()
    return row[0]


def compare(old: dict[str, Book], new: dict[str, Book], has_previous: bool = True) -> Comparison:
    # Compare only categories present in BOTH runs. Otherwise a quick partial run
    # (--categories 3) after a full one would report ~900 books as "removed",
    # and the next full run would report them as "new".
    common = {b.category for b in old.values()} & {b.category for b in new.values()}
    old = {url: b for url, b in old.items() if b.category in common}
    new = {url: b for url, b in new.items() if b.category in common}

    changed = [
        PriceChange(b.title, b.category, url, old[url].price, b.price)
        for url, b in new.items()
        if url in old and old[url].price != b.price
    ]
    changed.sort(key=lambda c: c.diff_percent)  # biggest discounts first
    added = [b for url, b in new.items() if url not in old] if has_previous else []
    removed = [b for url, b in old.items() if url not in new]
    return Comparison(changed, added, removed, has_previous)
