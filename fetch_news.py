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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Safety net for feeds that hang
socket.setdefaulttimeout(12)

OUTPUT_FILE = "news.json"


# ============================================================
# RSS SOURCES
# ============================================================
# Notes:
# - HN "points=10" was too strict for niche topics.
#   Removed points filter, added real sources per category.

FEED_SOURCES = {
    "AI Failures": [
        "https://hnrss.org/newest?q=AI+failure",
        "https://hnrss.org/newest?q=AI+hallucination",
        "https://hnrss.org/newest?q=chatbot+wrong",
        "https://hnrss.org/newest?q=AI+incident",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.technologyreview.com/feed/",
    ],
    "AI Security": [
        "https://hnrss.org/newest?q=AI+security",
        "https://hnrss.org/newest?q=AI+jailbreak",
        "https://hnrss.org/newest?q=prompt+injection",
        "https://hnrss.org/newest?q=LLM+vulnerability",
        "https://feeds.feedburner.com/TheHackersNews",
        "https://www.bleepingcomputer.com/feed/",
    ],
    "AI Outages": [
        "https://hnrss.org/newest?q=AI+outage",
        "https://hnrss.org/newest?q=ChatGPT+down",
        "https://hnrss.org/newest?q=OpenAI+outage",
        "https://hnrss.org/newest?q=AI+service+down",
        "https://www.theverge.com/rss/index.xml",
    ],
    "Tech Failures": [
        "https://hnrss.org/newest?q=tech+outage",
        "https://hnrss.org/newest?q=service+outage",
        "https://hnrss.org/newest?q=software+failure",
        "https://arstechnica.com/feed/",
        "https://www.theregister.com/headlines.atom",
    ],
    "Company Milestones": [
        "https://techcrunch.com/feed/",
        "https://www.cio.com/feed/",
        "https://venturebeat.com/feed/",
    ],
    "General Tech": [
        "https://www.theverge.com/rss/index.xml",
        "https://news.ycombinator.com/rss",
        "https://arstechnica.com/feed/",
    ],
}


# ============================================================
# FALLBACK IMAGES (rotated by URL hash)
# ============================================================

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1655720828018-edd2daec9349?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
]


def pick_fallback(url):
    return FALLBACK_IMAGES[hash(url) % len(FALLBACK_IMAGES)]


# ============================================================
# REQUEST HEADERS
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
    "hallucinated": 10, "misinformation": 7, "misleading": 5,
    "bug": 6, "broken": 7, "malfunction": 8, "glitch": 6, "problem": 4,
}

SECURITY_WORDS = {
    "security": 8, "hack": 8, "hacked": 9, "attack": 7,
    "vulnerability": 10, "vulnerable": 8, "exploit": 10,
    "jailbreak": 10, "prompt injection": 12, "data leak": 12,
    "breach": 12, "malware": 10, "phishing": 8,
}

OUTAGE_WORDS = {
    "outage": 12, "down": 8, "downtime": 10, "offline": 8,
    "unavailable": 9, "service disruption": 10, "disruption": 8,
    "server issue": 8,
}

MILESTONE_WORDS = {
    "launch": 6, "launched": 6, "release": 6, "released": 6,
    "funding": 8, "raised": 7, "valuation": 8, "acquisition": 9,
    "acquired": 9, "partnership": 6, "million": 5, "billion": 7,
    "record": 5,
}


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_html(raw):
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(" ")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(text, length=220):
    text = text.strip()
    if len(text) <= length:
        return text
    cut = text[:length - 3]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "..."


def normalize_url(url):
    return url.strip().split("#")[0].rstrip("/").lower()


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
        "venturebeat.com": "VentureBeat",
        "technologyreview.com": "MIT Tech Review",
        "bleepingcomputer.com": "BleepingComputer",
        "feeds.feedburner.com": "The Hacker News",
        "thehackernews.com": "The Hacker News",
        "theregister.com": "The Register",
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
                tzinfo=datetime.timezone.utc
            ).isoformat()
        if entry.get("updated_parsed"):
            return datetime.datetime(
                *entry.updated_parsed[:6],
                tzinfo=datetime.timezone.utc
            ).isoformat()
    except Exception:
        pass
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ============================================================
# SCORE
# ============================================================

def calculate_score(title, summary):
    text = f"{title} {summary}".lower()
    score = 0
    for words in (FAILURE_WORDS, SECURITY_WORDS, OUTAGE_WORDS, MILESTONE_WORDS):
        for word, value in words.items():
            if word in text:
                score += value
    return score


# ============================================================
# INCIDENT TYPE
# ============================================================

def detect_incident_type(title, summary, section):
    text = f"{title} {summary}".lower()
    if any(w in text for w in OUTAGE_WORDS):
        return "Outage"
    if any(w in text for w in SECURITY_WORDS):
        return "Security"
    if any(w in text for w in FAILURE_WORDS):
        return "Failure"
    if section == "Company Milestones":
        return "Milestone"
    return "News"


# ============================================================
# STATUS
# ============================================================

def detect_status(title, summary, section):
    text = f"{title} {summary}".lower()
    if any(w in text for w in ["confirmed", "official", "company confirmed", "company said"]):
        return "Confirmed"
    if section == "Company Milestones":
        return "Announced"
    return "Reported"


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_og_image(article_url):
    try:
        res = requests.get(
            article_url,
            headers=HEADERS,
            timeout=7,
            stream=True
        )
        if res.status_code != 200:
            return None

        chunks = []
        total = 0
        for chunk in res.iter_content(8192):
            chunks.append(chunk)
            total += len(chunk)
            if total > 150_000:
                break
            if b"</head>" in b"".join(chunks).lower():
                break

        data = b"".join(chunks)
        soup = BeautifulSoup(data, "html.parser")

        for attr, val in [
            ("property", "og:image"),
            ("property", "og:image:secure_url"),
            ("name", "twitter:image"),
            ("name", "twitter:image:src"),
        ]:
            tag = soup.find("meta", attrs={attr: val})
            if tag and tag.get("content"):
                content = tag["content"].strip()
                if content.startswith("http"):
                    return content

        img = soup.find("img")
        if img:
            src = img.get("src", "")
            if src.startswith("http"):
                return src
    except Exception as e:
        logging.debug("Image extraction failed for %s: %s", article_url, e)

    return None


# ============================================================
# FETCH RSS
# ============================================================

def fetch_feed(feed_url, section):
    articles = []
    try:
        logging.info("Reading %s", feed_url)
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:10]:
            link = normalize_url(entry.get("link", ""))
            if not link:
                continue
            if get_domain(link) == "news.ycombinator.com" and "/item" in link:
                continue

            title = clean_html(entry.get("title", "Untitled"))
            summary = clean_html(
                entry.get("summary")
                or entry.get("description")
                or ""
            )
            if not title:
                continue

            articles.append({
                "title": title,
                "url": link,
                "section": section,
                "incident_type": detect_incident_type(title, summary, section),
                "source": source_name(link),
                "image_url": None,
                "summary": truncate(summary),
                "published": to_iso(entry),
                "score": calculate_score(title, summary),
                "status": detect_status(title, summary, section),
            })
    except Exception as e:
        logging.error("Feed error %s: %s", feed_url, e)

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

    tasks = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for section, feeds in FEED_SOURCES.items():
            for feed_url in feeds:
                tasks.append(executor.submit(fetch_feed, feed_url, section))

        for task in as_completed(tasks):
            try:
                for article in task.result():
                    if article["url"] in seen:
                        continue
                    seen.add(article["url"])
                    articles.append(article)
            except Exception as e:
                logging.error("Worker error: %s", e)

    if not articles:
        logging.error("No articles collected.")
        return

    logging.info("Collected %d unique articles.", len(articles))

    # Sort + slice BEFORE fetching images (much faster)
    articles.sort(
        key=lambda a: (a.get("published", ""), a.get("score", 0)),
        reverse=True
    )
    articles = articles[:80]

    logging.info("Fetching images for %d articles...", len(articles))

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {
            executor.submit(extract_og_image, a["url"]): a
            for a in articles
        }
        for future in as_completed(future_map):
            art = future_map[future]
            try:
                art["image_url"] = future.result() or pick_fallback(art["url"])
            except Exception:
                art["image_url"] = pick_fallback(art["url"])

    for idx, art in enumerate(articles, 1):
        art["rank"] = idx

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)

    from collections import Counter
    counts = Counter(a["section"] for a in articles)
    for section, count in counts.items():
        logging.info("  %-22s %d", section, count)

    logging.info("Saved %d articles to %s", len(articles), OUTPUT_FILE)
    logging.info("=" * 60)


if __name__ == "__main__":
    fetch_news()