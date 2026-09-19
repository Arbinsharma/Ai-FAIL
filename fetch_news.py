import json
import logging
import datetime
import html as html_lib
import os
import random
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

socket.setdefaulttimeout(12)
OUTPUT_FILE = "news.json"
POSTED_CACHE_FILE = "posted_cache.txt"
WEBHOOK_URL = "https://hook.eu1.make.com/eu46gj3m60wz2ghkipo4pblnoxdfe1dh"

# Categorized Feed Sources
FEED_SOURCES = {
    "AI Failures": [
        {"url": "https://hnrss.org/newest?q=AI+failure", "sub": "Incident"},
        {"url": "https://hnrss.org/newest?q=AI+hallucination", "sub": "Hallucination"},
        {"url": "https://hnrss.org/newest?q=AI+gone+wrong", "sub": "Critical"},
        {"url": "https://hnrss.org/newest?q=prompt+injection", "sub": "Jailbreak"},
        {"url": "https://hnrss.org/newest?q=LLM+exploit", "sub": "Security"},
        {"url": "https://hnrss.org/newest?q=ChatGPT+down", "sub": "Outage"},
        {"url": "https://hnrss.org/newest?q=OpenAI+incident", "sub": "Critical"},
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
    ]
}

AI_STRICT_FAILURES = [
    "fail", "hallucinat", "exploit", "jailbreak", "prompt injection",
    "rogue", "malfunction", "breach", "leak", "outage", "destruct",
    "catastroph", "broken", "danger", "vulnerability", "wrong answer",
    "unhinged", "bias", "incident", "crash", "down"
]

VIRAL_TERMS = [
    "hallucinat", "jailbreak", "exploit", "breach", "leak", "banned",
    "lawsuit", "disaster", "catastroph", "rogue", "chaos", "scam",
    "broken", "down", "outage", "fired", "danger", "shocking"
]

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1655720828018-edd2daec9349?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
]

def pick_fallback(url):
    return FALLBACK_IMAGES[zlib.adler32(url.encode("utf-8")) % len(FALLBACK_IMAGES)]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ne;q=0.8",
}

def clean_html(raw):
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    return re.sub(r"\s+", " ", html_lib.unescape(soup.get_text(" "))).strip()

def truncate(text, length=210):
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
        "theverge.com": "The Verge",
        "arstechnica.com": "Ars Technica",
        "thehackernews.com": "The Hacker News",
        "bleepingcomputer.com": "BleepingComputer",
        "techcrunch.com": "TechCrunch",
        "news.ycombinator.com": "Hacker News",
        "hnrss.org": "Hacker News",
    }
    return mapping.get(domain, domain or "Intelligence")

def detect_sub_niche(title, summary, default_sub="General"):
    text = f"{title} {summary}".lower()
    if any(w in text for w in ["politics", "election", "government", "minister", "neta", "parliament"]):
        return "Politics"
    if any(w in text for w in ["gadget", "software", "app", "tech", "hardware", "device"]):
        return "Tech"
    if any(w in text for w in ["hallucinat", "wrong answer", "delusion"]):
        return "Hallucination"
    if any(w in text for w in ["jailbreak", "injection", "override", "bypass"]):
        return "Jailbreak"
    if any(w in text for w in ["outage", "down", "offline", "crash", "blackout"]):
        return "Outage"
    if any(w in text for w in ["exploit", "leak", "breach", "hack", "vulnerability"]):
        return "Security"
    return default_sub

def calculate_viral_score(art):
    text = f"{art.get('title', '')} {art.get('summary', '')}".lower()
    score = sum(text.count(term) * 3 for term in VIRAL_TERMS)
    if art.get("section") == "AI Failures":
        score += 5
    if any(k in art.get("title", "").lower() for k in ["hallucinat", "fail", "broken", "exploit", "jailbreak"]):
        score += 8
    return score

def load_posted_cache():
    if not os.path.exists(POSTED_CACHE_FILE):
        return set()
    with open(POSTED_CACHE_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def mark_as_posted(url):
    with open(POSTED_CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(f"{url}\n")

def post_single_random_viral(articles):
    """Picks exactly 1 random, never-before-posted viral article and pushes it."""
    if not articles:
        return

    posted_urls = load_posted_cache()

    # Filter candidates that haven't been posted yet
    unposted = [a for a in articles if a["url"] not in posted_urls]
    if not unposted:
        logging.info("All current articles have already been posted to Facebook. No duplicate sent.")
        return

    # Prioritize items with positive viral score
    viral_pool = [a for a in unposted if calculate_viral_score(a) > 0]
    
    # If none scored positive on strict terms, choose from top recent unposted
    if not viral_pool:
        viral_pool = unposted[:10]

    # Pick 1 at random from the viral pool
    chosen = random.choice(viral_pool)

    payload = {
        "headline": f"🚨 AI FAIL ALERT: {chosen['title']}",
        "link": chosen["url"],
        "summary": chosen["summary"]
    }

    try:
        res = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code in (200, 202):
            mark_as_posted(chosen["url"])
            logging.info("[POSTED TO FACEBOOK] %s", chosen["title"])
        else:
            logging.warning("Make.com returned status %d for %s", res.status_code, chosen["title"])
    except Exception as e:
        logging.error("Failed sending webhook for %s: %s", chosen["title"], e)

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
            if total > 150_000 or b"</head>" in b"".join(chunks).lower():
                break

        soup = BeautifulSoup(b"".join(chunks), "html.parser")
        for attr, val in [("property", "og:image"), ("property", "og:image:secure_url"), ("name", "twitter:image")]:
            tag = soup.find("meta", attrs={attr: val})
            if tag and tag.get("content") and tag["content"].strip().startswith("http"):
                return tag["content"].strip()
    except Exception:
        pass
    return None

def fetch_feed(feed_info, section):
    feed_url = feed_info["url"]
    default_sub = feed_info["sub"]
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:20]:
            link = normalize_url(entry.get("link", ""))
            if not link or ("/item?id=" in link and "news.ycombinator.com" in link):
                continue

            title = clean_html(entry.get("title", ""))
            summary = clean_html(entry.get("summary") or entry.get("description") or "")
            if not title:
                continue

            if section == "AI Failures":
                combined = f"{title} {summary}".lower()
                if not any(trigger in combined for trigger in AI_STRICT_FAILURES):
                    continue

            articles.append({
                "title": title,
                "url": link,
                "section": section,
                "sub_niche": detect_sub_niche(title, summary, default_sub),
                "source": source_name(link),
                "image_url": None,
                "summary": truncate(summary),
                "published": to_iso(entry),
            })
    except Exception as e:
        logging.error("Feed error %s: %s", feed_url, e)
    return articles

def fetch_news():
    articles = []
    seen = set()
    tasks = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        for section, feeds in FEED_SOURCES.items():
            for feed_info in feeds:
                tasks.append(executor.submit(fetch_feed, feed_info, section))

        for task in as_completed(tasks):
            for art in task.result():
                if art["url"] in seen:
                    continue
                seen.add(art["url"])
                articles.append(art)

    if not articles:
        logging.warning("No articles fetched.")
        return

    articles.sort(key=lambda a: a.get("published", ""), reverse=True)
    articles = articles[:100]

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(extract_og_image, a["url"]): a for a in articles}
        for future in as_completed(future_map):
            art = future_map[future]
            try:
                art["image_url"] = future.result() or pick_fallback(art["url"])
            except Exception:
                art["image_url"] = pick_fallback(art["url"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)

    logging.info("Complete! Saved %d items to %s", len(articles), OUTPUT_FILE)

    # Automatically post 1 non-repetitive random viral article to Facebook
    post_single_random_viral(articles)

if __name__ == "__main__":
    fetch_news()