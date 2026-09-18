import json
import logging
import datetime
import html as html_lib
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import feedparser


# ============================================================
# AIFAIL NEWS ENGINE
# AI failures • security • outages • tech failures • milestones
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

OUTPUT_FILE = "news.json"

# Global socket timeout so feedparser (which uses urllib) can't hang
socket.setdefaulttimeout(10)


# ============================================================
# RSS SOURCES
# ============================================================

FEED_SOURCES = {
    "AI Failures": [
        "https://hnrss.org/newest?q=AI+failure&points=10",
        "https://hnrss.org/newest?q=AI+hallucination&points=10",
        "https://hnrss.org/newest?q=AI+incident&points=10",
        "https://hnrss.org/newest?q=AI+misalignment&points=10",
        "https://hnrss.org/newest?q=chatbot+wrong&points=10",
    ],
    "AI Security": [
        "https://hnrss.org/newest?q=AI+security&points=10",
        "https://hnrss.org/newest?q=AI+jailbreak&points=10",
        "https://hnrss.org/newest?q=prompt+injection&points=10",
        "https://hnrss.org/newest?q=LLM+vulnerability&points=10",
    ],
    "AI Outages": [
        "https://hnrss.org/newest?q=AI+outage&points=10",
        "https://hnrss.org/newest?q=ChatGPT+down&points=10",
        "https://hnrss.org/newest?q=OpenAI+outage&points=10",
        "https://hnrss.org/newest?q=AI+service+down&points=10",
    ],
    "Tech Failures": [
        "https://hnrss.org/newest?q=tech+outage&points=10",
        "https://hnrss.org/newest?q=service+outage&points=10",
        "https://hnrss.org/newest?q=software+failure&points=10",
        "https://arstechnica.com/feed/",
    ],
    "Company Milestones": [
        "https://techcrunch.com/feed/",
        "https://www.cio.com/feed/",
    ],
    "General Tech": [
        "https://www.theverge.com/rss/index.xml",
        "https://news.ycombinator.com/rss",
    ],
}


# ============================================================
# FALLBACK IMAGES (rotated by URL hash so grid doesn't look
# like the same placeholder tile repeated)
# ============================================================

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1655720828018-edd2daec9349?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=1200&q=80",
]


def pick_fallback(url):
    """Deterministic fallback so the same URL always maps to the same image."""
    if not url:
        return FALLBACK_IMAGES[0]
    return FALLBACK_IMAGES[hash(url) % len(FALLBACK_IMAGES)]


# ============================================================
# REQUEST SETTINGS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# KEYWORDS
# ============================================================

FAILURE_WORDS = {
    "failure": 8, "failed": 8, "fails": 8, "crash": 7, "crashed": 7,
    "error": 6, "wrong": 4, "incorrect": 5, "hallucination": 10,
    "hallucinated": 10, "misinformation": 7, "misleading": 5, "bug": 6,
    "broken": 7, "malfunction": 8, "glitch": 6, "problem": 4,
}

SECURITY_WORDS = {
    "security": 8, "hack": 8, "hacked": 9, "attack": 7, "vulnerability": 10,
    "vulnerable": 8, "exploit": 10, "jailbreak": 10, "prompt injection": 12,
    "data leak": 12, "breach": 12, "malware": 10, "phishing": 8,
}

OUTAGE_WORDS = {
    "outage": 12, "down": 8, "downtime": 10, "offline": 8, "unavailable": 9,
    "service disruption": 10, "disruption": 8, "server issue": 8,
}

MILESTONE_WORDS = {
    "launch": 6, "launched": 6, "release": 6, "released": 6, "funding": 8,
    "raised": 7, "valuation": 8, "acquisition": 9, "acquired": 9,
    "partnership": 6, "million": 5, "billion": 7, "record": 5,
}


# ---- Compile word-boundary regexes once ----------------------
# Prevents false positives like "down" matching "download",
# "wrong" matching "wrongdoing", etc.

def _compile(words):
    return {
        re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE): weight
        for w, weight in words.items()
    }


FAILURE_RE = _compile(FAILURE_WORDS)
SECURITY_RE = _compile(SECURITY_WORDS)
OUTAGE_RE = _compile(OUTAGE_WORDS)
MILESTONE_RE = _compile(MILESTONE_WORDS)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_html(raw):
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(" ")
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate(text, length=220):
    text = (text or "").strip()
    if len(text) <= length:
        return text
    cut = text[: length - 3]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "..."


def normalize_url(url):
    return (url or "").strip().split("#")[0]


def dedupe_key(url):
    """Lowercase, strip trailing slash, drop www."""
    url = normalize_url(url).lower()
    if url.endswith("/"):
        url = url[:-1]
    url = url.replace("://www.", "://", 1)
    return url


def get_domain(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def source_name(url):
    domain = get_domain(url)
    mapping = {
        "techcrunch.com": "TechCrunch",
        "arstechnica.com": "Ars Technica",
        "theverge.com": "The Verge",
        "news.ycombinator.com": "Hacker News",
        "cio.com": "CIO",
        "hnrss.org": "Hacker News",
    }
    return mapping.get(domain, domain or "Unknown Source")


# ============================================================
# DATE
# ============================================================

def to_iso(entry):
    try:
        if entry.get("published_parsed"):
            return datetime.datetime(
                *entry.published_parsed[:6],
                tzinfo=datetime.timezone.utc,
            ).isoformat()
        if entry.get("updated_parsed"):
            return datetime.datetime(
                *entry.updated_parsed[:6],
                tzinfo=datetime.timezone.utc,
            ).isoformat()
    except Exception:
        pass
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ============================================================
# SCORE
# ============================================================

def calculate_score(title, summary):
    text = f"{title} {summary}"
    score = 0
    for pattern, weight in FAILURE_RE.items():
        if pattern.search(text):
            score += weight
    for pattern, weight in SECURITY_RE.items():
        if pattern.search(text):
            score += weight
    for pattern, weight in OUTAGE_RE.items():
        if pattern.search(text):
            score += weight
    for pattern, weight in MILESTONE_RE.items():
        if pattern.search(text):
            score += weight
    return score


# ============================================================
# INCIDENT TYPE
# ============================================================

def _any_match(text, patterns):
    return any(p.search(text) for p in patterns)


def detect_incident_type(title, summary, section):
    text = f"{title} {summary}"

    if _any_match(text, OUTAGE_RE):
        return "Outage"
    if _any_match(text, SECURITY_RE):
        return "Security"
    if _any_match(text, FAILURE_RE):
        return "Failure"
    if section == "Company Milestones":
        return "Milestone"
    return "News"


# ============================================================
# STATUS
# ============================================================

CONFIRMED_PHRASES = [
    "confirmed", "official", "investigation found",
    "company said", "company confirmed",
]

REPORTED_PHRASES = [
    "reported", "reports", "according to",
    "may have", "appears to", "users say",
]


def detect_status(title, summary, section):
    text = f"{title} {summary}".lower()

    if any(p in text for p in CONFIRMED_PHRASES):
        return "Confirmed"

    if section == "Company Milestones":
        return "Announced"

    if any(p in text for p in REPORTED_PHRASES):
        return "Reported"

    return "Reported"


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_feed_image(entry):
    """Try feed-provided images first — no HTTP request needed."""
    # media:content / media:thumbnail
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key)
        if media:
            for item in media:
                url = item.get("url", "")
                if url.startswith("http"):
                    return url

    # enclosures
    for enc in entry.get("enclosures", []) or []:
        href = enc.get("href", "")
        mime = enc.get("type", "")
        if href.startswith("http") and mime.startswith("image/"):
            return href

    return None


def extract_og_image(article_url):
    """Fetch a small range of the article HTML and look for og:image."""
    try:
        res = requests.get(
            article_url,
            headers={**HEADERS, "Range": "bytes=0-65536"},
            timeout=6,
        )
        if res.status_code >= 400:
            return None

        soup = BeautifulSoup(res.content, "html.parser")

        for attr, value in [
            ("property", "og:image"),
            ("property", "og:image:secure_url"),
            ("name", "twitter:image"),
            ("name", "twitter:image:src"),
        ]:
            tag = soup.find("meta", attrs={attr: value})
            if tag and tag.get("content"):
                img = tag["content"].strip()
                if img.startswith("http"):
                    return img

        img = soup.find("img")
        if img:
            src = img.get("src", "")
            if src.startswith("http"):
                return src

    except Exception as error:
        logging.debug("og:image failed for %s: %s", article_url, error)

    return None


# ============================================================
# FEED FETCH
# ============================================================

def fetch_feed(feed_url, section):
    """Fetch and parse a single RSS feed, returning a list of article dicts."""
    articles = []

    try:
        res = requests.get(feed_url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        feed = feedparser.parse(res.content)

        for entry in feed.entries[:10]:
            link = normalize_url(entry.get("link", ""))
            if not link:
                continue

            # Skip HN self-post discussion pages (rare, but noise)
            if get_domain(link) == "news.ycombinator.com":
                continue

            title = clean_html(entry.get("title", "Untitled"))
            summary = clean_html(
                entry.get("summary") or entry.get("description") or ""
            )

            if not title:
                continue

            articles.append({
                "title": title,
                "url": link,
                "section": section,
                "incident_type": detect_incident_type(title, summary, section),
                "source": source_name(link),
                "image_url": extract_feed_image(entry),  # may be None
                "summary": truncate(summary),
                "published": to_iso(entry),
                "score": calculate_score(title, summary),
                "status": detect_status(title, summary, section),
            })

    except Exception as error:
        logging.error("Feed error %s: %s", feed_url, error)

    return articles


# ============================================================
# MAIN
# ============================================================

def fetch_news():
    logging.info("=" * 60)
    logging.info("AIFAIL NEWS ENGINE STARTING")
    logging.info("=" * 60)

    articles = []
    seen = set()

    # ---- Fetch all feeds concurrently ----------------------
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(fetch_feed, url, section)
            for section, feeds in FEED_SOURCES.items()
            for url in feeds
        ]

        for future in as_completed(futures):
            try:
                for article in future.result():
                    key = dedupe_key(article["url"])
                    if key in seen:
                        continue
                    seen.add(key)
                    articles.append(article)
            except Exception as error:
                logging.error("Worker error: %s", error)

    if not articles:
        logging.error("No articles collected.")
        return

    logging.info("Collected %d unique articles.", len(articles))

    # ---- Sort + slice BEFORE image fetching ----------------
    articles.sort(
        key=lambda a: (a.get("published", ""), a.get("score", 0)),
        reverse=True,
    )
    articles = articles[:80]

    logging.info("Keeping top %d articles.", len(articles))

    # ---- Only fetch og:image for articles missing one ------
    need_image = [a for a in articles if not a.get("image_url")]
    have_image = len(articles) - len(need_image)

    logging.info(
        "Images: %d from feed, %d need scraping.",
        have_image,
        len(need_image),
    )

    if need_image:
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_map = {
                executor.submit(extract_og_image, a["url"]): a
                for a in need_image
            }
            for future in as_completed(future_map):
                article = future_map[future]
                try:
                    article["image_url"] = future.result()
                except Exception:
                    article["image_url"] = None

    # ---- Apply fallback to any still-missing images --------
    for article in articles:
        if not article.get("image_url"):
            article["image_url"] = pick_fallback(article["url"])

    # ---- Rank -----------------------------------------------
    for idx, article in enumerate(articles, start=1):
        article["rank"] = idx

    # ---- Write ----------------------------------------------
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(articles, file, indent=2, ensure_ascii=False)

    logging.info("Saved %d articles to %s", len(articles), OUTPUT_FILE)
    logging.info("=" * 60)
    logging.info("AIFAIL NEWS ENGINE FINISHED")
    logging.info("=" * 60)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    fetch_news()