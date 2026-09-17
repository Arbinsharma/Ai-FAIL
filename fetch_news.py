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

FEED_SOURCES = {
    "AI Failures": [
        "https://hnrss.org/newest?q=AI+failure&points=20",
        "https://hnrss.org/newest?q=hallucination+AI&points=20",
    ],
    "Tech Failures": [
        "https://arstechnica.com/feed/",
        "https://hnrss.org/newest?q=outage&points=20",
    ],
    "Company Milestones": [
        "https://techcrunch.com/feed/",
        "https://www.cio.com/feed/",
    ],
    "General Tech": [
        "https://www.theverge.com/rss/index.xml",
        "https://news.ycombinator.com/rss",
    ]
}

FALLBACK_IMG = (
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe"
    "?auto=format&fit=crop&w=800&q=80"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def clean_html(raw):
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()

def truncate(s, n=180):
    s = s.strip()
    return s if len(s) <= n else s[:n-3].rsplit(" ", 1)[0] + "…"

def to_iso(entry):
    if entry.get("published_parsed"):
        return datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc).isoformat()
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def extract_og_image(article_url):
    try:
        with requests.get(article_url, headers=HEADERS, timeout=5, stream=True) as r:
            if r.status_code != 200:
                return None
            buf = b""
            for chunk in r.iter_content(8192):
                buf += chunk
                if b"</head>" in buf or len(buf) > 100_000:
                    break
        soup = BeautifulSoup(buf, "html.parser")
        for prop in ("og:image", "og:image:secure_url", "twitter:image"):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                return tag["content"]
        img = soup.find("img")
        if img and img.get("src", "").startswith("http"):
            return img["src"]
    except Exception:
        pass
    return None

def fetch_news():
    logging.info("Starting categorized news fetch...")
    articles = []
    seen = set()

    for section_name, feeds in FEED_SOURCES.items():
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:4]:
                    link = (entry.get("link") or "").strip()
                    if not link or link in seen or "news.ycombinator.com/item" in link:
                        continue
                    seen.add(link)

                    title = clean_html(entry.get("title", "Untitled"))
                    summary = clean_html(entry.get("summary") or entry.get("description") or "")

                    articles.append({
                        "title": html_lib.escape(title),
                        "url": link,
                        "section": section_name,
                        "image_url": None,
                        "summary": html_lib.escape(truncate(summary)),
                        "published": to_iso(entry),
                    })
            except Exception as e:
                logging.error(f"Feed error {feed_url}: {e}")

    if not articles:
        return

    logging.info(f"Scraping images for {len(articles)} articles...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        images = list(pool.map(extract_og_image, [a["url"] for a in articles]))

    for article, img in zip(articles, images):
        article["image_url"] = img if img else FALLBACK_IMG

    articles.sort(key=lambda a: a["published"], reverse=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)

    logging.info(f"Successfully saved {len(articles)} articles with sections!")

if __name__ == "__main__":
    fetch_news()
