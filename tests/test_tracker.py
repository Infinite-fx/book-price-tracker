"""Offline tests: parsing on a saved HTML snippet + comparison logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import Book, parse_categories, parse_listing  # noqa: E402
from storage import Run, compare, connect, previous_run, save_run  # noqa: E402

PAGE_URL = "https://books.toscrape.com/catalogue/category/books/poetry_23/index.html"

LISTING_HTML = """
<div class="side_categories"><ul><li><a href="/">Books</a><ul>
  <li><a href="catalogue/category/books/travel_2/index.html">Travel</a></li>
  <li><a href="catalogue/category/books/poetry_23/index.html">Poetry</a></li>
</ul></li></ul></div>
<article class="product_pod">
  <p class="star-rating Three"></p>
  <h3><a href="../../../a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light...</a></h3>
  <p class="price_color">£51.77</p>
  <p class="instock availability">In stock</p>
</article>
<article class="product_pod">
  <p class="star-rating One"></p>
  <h3><a href="../../../other_1/index.html" title="Other">Other</a></h3>
  <p class="price_color">£10.00</p>
  <p class="availability">Out of stock</p>
</article>
<ul class="pager"><li class="next"><a href="page-2.html">next</a></li></ul>
"""


def book(url: str, price: float) -> Book:
    return Book(url, url.upper(), "Cat", price, 3, True)


def test_parse_listing():
    books, next_url = parse_listing(LISTING_HTML, PAGE_URL, "Poetry")
    assert len(books) == 2
    first = books[0]
    assert first.title == "A Light in the Attic"
    assert first.price == 51.77
    assert first.rating == 3
    assert first.in_stock is True
    assert first.url == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    assert books[1].in_stock is False
    assert next_url == "https://books.toscrape.com/catalogue/category/books/poetry_23/page-2.html"


def test_parse_last_page_has_no_next():
    _, next_url = parse_listing("<article></article>", PAGE_URL, "Poetry")
    assert next_url is None


def test_parse_categories():
    cats = parse_categories(LISTING_HTML, "https://books.toscrape.com/")
    assert [name for name, _ in cats] == ["Travel", "Poetry"]
    assert cats[0][1] == "https://books.toscrape.com/catalogue/category/books/travel_2/index.html"


FULL = Run(1, None)


def partial(*cats: str) -> Run:
    return Run(2, set(cats))


def test_compare_finds_changes_new_and_removed():
    old = {"a": book("a", 10.0), "b": book("b", 20.0), "gone": book("gone", 5.0)}
    new = {"a": book("a", 8.0), "b": book("b", 20.0), "fresh": book("fresh", 7.0)}
    cmp = compare(old, new, FULL, FULL)
    assert [(c.url, c.diff) for c in cmp.changed] == [("a", -2.0)]
    assert round(cmp.changed[0].diff_percent, 2) == -0.2
    assert [b.url for b in cmp.new] == ["fresh"]
    assert [b.url for b in cmp.removed] == ["gone"]


def test_brand_new_category_counts_as_new_after_full_run():
    old = {"a": book("a", 10.0)}
    new = {"a": book("a", 10.0), "n": Book("n", "N", "Brand New", 9.0, 3, True)}
    assert [b.url for b in compare(old, new, FULL, FULL).new] == ["n"]


def test_partial_run_does_not_report_unchecked_categories_as_removed():
    old = {"a": book("a", 10.0), "x": Book("x", "X", "Other", 5.0, 3, True)}
    new = {"a": book("a", 10.0)}  # quick run that checked only "Cat"
    cmp = compare(old, new, FULL, partial("Cat"))
    assert cmp.removed == [] and cmp.new == [] and cmp.changed == []


def test_partial_run_still_finds_removed_and_new_inside_its_categories():
    old = {"a": book("a", 10.0), "gone": book("gone", 5.0)}
    new = {"a": book("a", 10.0), "fresh": book("fresh", 7.0)}
    cmp = compare(old, new, FULL, partial("Cat"))
    assert [b.url for b in cmp.removed] == ["gone"]
    assert [b.url for b in cmp.new] == ["fresh"]


def test_full_run_after_partial_does_not_call_unchecked_books_new():
    old = {"a": book("a", 10.0)}
    new = {"a": book("a", 10.0), "x": Book("x", "X", "Other", 5.0, 3, True)}
    assert compare(old, new, partial("Cat"), FULL).new == []


def test_first_run_reports_nothing():
    cmp = compare({}, {"a": book("a", 1.0)}, None, FULL)
    assert cmp.changed == [] and cmp.new == [] and cmp.removed == []
    assert cmp.has_previous is False


def test_full_run_is_compared_with_last_full_run(tmp_path):
    conn = connect(str(tmp_path / "h.db"))
    full = save_run(conn, [book("a", 1.0)], None)
    save_run(conn, [book("a", 1.0)], ["Cat"])  # quick test run in between
    assert previous_run(conn, full=True).id == full.id
    assert previous_run(conn, full=False).scope == {"Cat"}
