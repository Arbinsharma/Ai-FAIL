import json
import logging
import datetime
import html as html_lib
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup
import feedparser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

OUTPUT_FILE = "news.json"

# Real publisher feeds — these reliably have og:image tags
FEEDS = [
    "https://www.theverge.com/rss/index.xml",
    "https://arstechnica.com/feed/",
    "https://techcrunch.com/feed/",
    "https://www.cio.com/feed/",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://hnrss.org/newest?q=AI&points=50",   # only high-point AI stories
]

FALLBACK_IMG = (
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe"
    "?auto=format&fit=crop&w=800&q=80"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_html(raw):
    """Strip HTML tags and unescape entities from an RSS snippet."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(s, n=200):
    s = s.strip()
    if len(s) <= n:
        return s
    return s[: n - 3].rsplit(" ", 1)[0] + "…"


def to_iso(entry):
    if entry.get("published_parsed"):
        return datetime.datetime(
            *entry.published_parsed[:6], tzinfo=datetime.timezone.utc
        ).isoformat()
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def extract_og_image(article_url):
    """
    Fetch only the <head> of the article and pull the primary cover image.
    Returns the real image URL, or None if the page has no OG/twitter image.
    """
    try:
        with requests.get(
            article_url, headers=HEADERS, timeout=4, stream=True
        ) as r:
            if r.status_code != 200:
                return None
            # Read just enough of the page to capture <head>
            buf = b""
            for chunk in r.iter_content(8192):
                buf += chunk
                if b"</head>" in buf or len(buf) > 80_000:
                    break

        soup = BeautifulSoup(buf, "html.parser")

        # 1. Open Graph image (most common)
        for attr in ("property", "name"):
            tag = soup.find("meta", attrs={attr: "og:image"})
            if tag and tag.get("content"):
                return tag["content"]

        # 2. Twitter card image
        for attr in ("property", "name"):
            tag = soup.find("meta", attrs={attr: "twitter:image"})
            if tag and tag.get("content"):
                return tag["content"]

        # 3. Fallback: first large-looking <img> in the page
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src.startswith("http") and any(
                ext in src.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")
            ):
                return src

    except Exception as e:
        logging.debug(f"Image scrape failed for {article_url}: {e}")

    return None


def is_scrapable(url):
    """Skip HN discussion pages and other non-article URLs."""
    if not url:
        return False
    if "news.ycombinator.com/item?id=" in url:
        return False
    if url.endswith((".pdf", ".zip")):
        return False
    return True


def fetch_news():
    logging.info("Starting news fetch...")
    articles = []
    seen = set()

    # --- Pass 1: Collect entries from all feeds ---
    for feed_url in FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:6]:
                link = (entry.get("link") or "").strip()
                if not is_scrapable(link) or link in seen:
                    continue
                seen.add(link)

                title = clean_html(entry.get("title", "Untitled"))
                summary = clean_html(
                    entry.get("summary") or entry.get("description") or ""
                )

                articles.append(
                    {
                        "title": html_lib.escape(title),
                        "url": link,
                        "image_url": None,  # filled in pass 2
                        "summary": html_lib.escape(truncate(summary)),
                        "published": to_iso(entry),
                    }
                )
        except Exception as e:
            logging.error(f"Feed error {feed_url}: {e}")

    if not articles:
        logging.warning("No articles fetched — leaving news.json untouched.")
        return

    # --- Pass 2: Scrape images in parallel ---
    logging.info(f"Scraping images for {len(articles)} articles in parallel...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        images = list(pool.map(extract_og_image, [a["url"] for a in articles]))

    hits = 0
    for article, img in zip(articles, images):
        if img:
            article["image_url"] = img
            hits += 1
        else:
            article["image_url"] = FALLBACK_IMG

    logging.info(f"Real images found: {hits}/{len(articles)}")
    logging.info(f"Fallback used: {len(articles) - hits}")

    # --- Pass 3: Sort newest first, write JSON ---
    articles.sort(key=lambda a: a["published"], reverse=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)

    logging.info(f"Saved {len(articles)} articles to {OUTPUT_FILE}")


if __name__ == "__main__":
    fetch_news()