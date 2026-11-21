"""Downloading and parsing pages of the shop.

Everything that knows about the site's HTML lives in this file.
To adapt the tracker to another shop, you only need to rewrite
the parse_* functions below.
"""

import time
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
HEADERS = {"User-Agent": "Mozilla/5.0 (book-price-tracker; portfolio project)"}
DELAY_SECONDS = 0.5  # pause between requests, so we don't overload the site
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


@dataclass
class Book:
    url: str
    title: str
    category: str
    price: float
    rating: int
    in_stock: bool


def fetch(session: requests.Session, url: str, retries: int = 3) -> str:
    """Download a page; on network errors try again a few times."""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            resp.encoding = "utf-8"  # otherwise "£" turns into "Â£"
            time.sleep(DELAY_SECONDS)
            return resp.text
        except requests.RequestException as err:
            if attempt == retries:
                raise
            print(f"  ! {url}: {err}, retry {attempt}/{retries - 1}")
            time.sleep(2 * attempt)
    raise AssertionError("unreachable")


def parse_categories(html: str, page_url: str) -> list[tuple[str, str]]:
    """List of (category name, category URL) from the sidebar."""
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select("div.side_categories ul li ul li a")
    return [(a.get_text(strip=True), urljoin(page_url, a["href"])) for a in links]


def parse_listing(html: str, page_url: str, category: str) -> tuple[list[Book], str | None]:
    """Books from one listing page + URL of the next page (or None)."""
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        price_text = card.select_one("p.price_color").get_text(strip=True)
        rating_word = card.select_one("p.star-rating")["class"][1]
        stock_text = card.select_one("p.availability").get_text(strip=True)
        books.append(Book(
            url=urljoin(page_url, link["href"]),
            title=link["title"],
            category=category,
            price=float(price_text.lstrip("£")),
            rating=RATINGS.get(rating_word, 0),
            in_stock="In stock" in stock_text,
        ))
    next_link = soup.select_one("li.next a")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return books, next_url


def scrape(max_categories: int | None = None) -> list[Book]:
    """Walk through all categories (and all their pages) and collect books."""
    session = requests.Session()
    categories = parse_categories(fetch(session, BASE_URL), BASE_URL)
    if max_categories:
        categories = categories[:max_categories]

    books: list[Book] = []
    for i, (name, url) in enumerate(categories, 1):
        print(f"[{i}/{len(categories)}] {name}")
        while url:
            page_books, url = parse_listing(fetch(session, url), url, name)
            books.extend(page_books)
    return books
