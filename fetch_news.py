import json
import logging
import datetime
import html as html_lib
import re
import socket
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urlsplit, urlunsplit

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
# RSS SOURCES WITH SUB-NICHE LABELS
# ============================================================
FEED_SOURCES = {
    "AI Failures": [
        {"url": "https://hnrss.org/newest?q=AI+failure", "sub": "Incident"},
        {"url": "https://hnrss.org/newest?q=AI+hallucination", "sub": "Hallucination"},
        {"url": "https://hnrss.org/newest?q=chatbot+wrong", "sub": "Failure"},
        {"url": "https://hnrss.org/newest?q=AI+incident", "sub": "Incident"},
        {"url": "https://hnrss.org/newest?q=AI+jailbreak", "sub": "Exploit"},
        {"url": "https://hnrss.org/newest?q=prompt+injection", "sub": "Vulnerability"},
        {"url": "https://hnrss.org/newest?q=OpenAI+outage", "sub": "Outage"},
        {"url": "https://feeds.feedburner.com/TheHackersNews", "sub": "Security"},
        {"url": "https://www.bleepingcomputer.com/feed/", "sub": "Security"},
    ],
    "Nepali News": [
        {"url": "https://ronbpost.com/feed", "sub": "General"},
        {"url": "https://techpana.com/feed", "sub": "Tech"},
    ],
    "General Tech": [
        {"url": "https://theverge.com/rss/index.xml", "sub": "Tech"},
        {"url": "https://arstechnica.com/feed/", "sub": "Tech"},
        {"url": "https://news.ycombinator.com/rss", "sub": "Discussion"},
        {"url": "https://techcrunch.com/feed/", "sub": "Milestones"},
        {"url": "https://www.theregister.com/headlines.atom", "sub": "Tech"},
    ]
}

# Strict filters to prioritize critical issues for AI Failures
AI_FAILURE_CRITICAL = [
    "failure", "fail", "destruct", "jailbreak", "prompt injection",
    "hallucinat", "malfunction", "exploit", "leak", "breach", "outage",
    "catastroph", "rogue", "attack", "vulnerability", "risk", "down"
]

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1655720828018-edd2daec9349?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
]

def pick_fallback(url):
    # Deterministic integer selection independent of Python session seed
    return FALLBACK_IMAGES[zlib.adler32(url.encode("utf-8")) % len(FALLBACK_IMAGES)]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ne;q=0.8",
}

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
    try:
        parts = urlsplit(url.strip())
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    except Exception:
        return url.strip().split("?")[0].rstrip("/").lower()

def get_domain(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""

def source_name(url):
    domain = get_domain(url)
    mapping = {
        "ronbpost.com": "RONB Post",
        "techpana.com": "TechPana",
        "techcrunch.com": "TechCrunch",
        "arstechnica.com": "Ars Technica",
        "theverge.com": "The Verge",
        "news.ycombinator.com": "Hacker News",
        "hnrss.org": "Hacker News",
        "venturebeat.com": "VentureBeat",
        "technologyreview.com": "MIT Tech Review",
        "bleepingcomputer.com": "BleepingComputer",
        "feeds.feedburner.com": "The Hacker News",
        "thehackernews.com": "The Hacker News",
        "theregister.com": "The Register",
    }
    return mapping.get(domain, domain or "Web")

def detect_sub_niche(title, summary, default_sub="General"):
    text = f"{title} {summary}".lower()
    if any(w in text for w in ["politics", "election", "government", "minister", "neta", "parliament"]):
        return "Politics"
    if any(w in text for w in ["tech", "ai", "gadget", "software", "app", "digital", "cyber"]):
        return "Tech"
    if any(w in text for w in ["outage", "down", "offline", "disruption"]):
        return "Outages"
    if any(w in text for w in ["hack", "exploit", "leak", "vulnerability", "breach"]):
        return "Security"
    return default_sub

def calculate_score(title, summary):
    text = f"{title} {summary}".lower()
    score = 0
    for words in (FAILURE_WORDS, SECURITY_WORDS, OUTAGE_WORDS):
        for word, value in words.items():
            if word in text:
                score += value
    return score

def detect_status(title, summary):
    text = f"{title} {summary}".lower()
    if any(w in text for w in ["confirmed", "official", "company confirmed", "company said"]):
        return "Confirmed"
    return "Reported"

def to_iso(entry):
    try:
        if entry.get("published_parsed"):
            return datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc).isoformat()
        if entry.get("updated_parsed"):
            return datetime.datetime(*entry.updated_parsed[:6], tzinfo=datetime.timezone.utc).isoformat()
    except Exception:
        pass
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def extract_og_image(article_url):
    try:
        res = requests.get(article_url, headers=HEADERS, timeout=7, stream=True)
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

        soup = BeautifulSoup(b"".join(chunks), "html.parser")
        for attr, val in [("property", "og:image"), ("property", "og:image:secure_url"), ("name", "twitter:image"), ("name", "twitter:image:src")]:
            tag = soup.find("meta", attrs={attr: val})
            if tag and tag.get("content"):
                content = tag["content"].strip()
                if content.startswith("http"):
                    return content

        img = soup.find("img")
        if img and img.get("src") and img["src"].startswith("http"):
            return img["src"]
    except Exception:
        pass
    return None

def fetch_feed(feed_info, section):
    feed_url = feed_info["url"]
    default_sub = feed_info["sub"]
    articles = []
    try:
        logging.info("Reading %s", feed_url)
        feed = feedparser.parse(feed_url)

        for entry in feed.entries[:15]:
            link = normalize_url(entry.get("link", ""))
            if not link:
                continue
            if get_domain(link) == "news.ycombinator.com" and "/item" in link:
                continue

            title = clean_html(entry.get("title", "Untitled"))
            summary = clean_html(entry.get("summary") or entry.get("description") or "")

            if not title:
                continue

            if section == "AI Failures":
                combined = f"{title} {summary}".lower()
                if not any(k in combined for k in AI_FAILURE_CRITICAL):
                    continue

            articles.append({
                "title": title,
                "url": link,
                "section": section,
                "sub_niche": detect_sub_niche(title, summary, default_sub),
                "incident_type": detect_sub_niche(title, summary, default_sub),
                "source": source_name(link),
                "image_url": None,
                "summary": truncate(summary),
                "published": to_iso(entry),
                "score": calculate_score(title, summary),
                "status": detect_status(title, summary),
            })
    except Exception as e:
        logging.error("Feed error %s: %s", feed_url, e)

    return articles

def fetch_news():
    logging.info("=" * 60)
    logging.info("AIFAIL INTELLIGENCE ENGINE RUNNING")
    logging.info("=" * 60)

    articles = []
    seen = set()
    tasks = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        for section, feeds in FEED_SOURCES.items():
            for feed_info in feeds:
                tasks.append(executor.submit(fetch_feed, feed_info, section))

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

    articles.sort(key=lambda a: (a.get("published", ""), a.get("score", 0)), reverse=True)
    articles = articles[:90]

    logging.info("Extracting images for %d articles...", len(articles))
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(extract_og_image, a["url"]): a for a in articles}
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

    logging.info("Successfully saved %d stories to %s", len(articles), OUTPUT_FILE)
    logging.info("=" * 60)

if __name__ == "__main__":
    fetch_news()