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

FEED_SOURCES = {
    "AI Failures": [
        {"url": "https://hnrss.org/newest?q=AI+failure", "sub": "Incident"},
        {"url": "https://hnrss.org/newest?q=AI+hallucination", "sub": "Hallucination"},
        {"url": "https://hnrss.org/newest?q=prompt+injection", "sub": "Jailbreak"},
        {"url": "https://hnrss.org/newest?q=LLM+exploit", "sub": "Security"},
        {"url": "https://hnrss.org/newest?q=ChatGPT+down", "sub": "Outage"},
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

AI_KEYWORDS = [
    "ai", "artificial intelligence", "llm", "chatgpt", "openai", 
    "gemini", "claude", "anthropic", "copilot", "deepseek", "model", "agent"
]

AI_STRICT_FAILURES = [
    "fail", "hallucinat", "exploit", "jailbreak", "prompt injection",
    "rogue", "malfunction", "breach", "leak", "outage", "destruct",
    "catastroph", "broken", "danger", "vulnerability", "wrong answer",
    "unhinged", "bias", "incident", "crash", "down", "hack"
]

MODEL_SIGNATURES = {
    "ChatGPT / OpenAI": ["chatgpt", "openai", "gpt-4", "gpt-5", "sora"],
    "Google Gemini": ["gemini", "deepmind", "google ai"],
    "Anthropic Claude": ["claude", "anthropic"],
    "Microsoft Copilot": ["copilot", "azure ai"],
    "Meta AI": ["llama", "meta ai"],
    "DeepSeek": ["deepseek"]
}

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1655720828018-edd2daec9349?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,ne;q=0.8",
}

def pick_fallback(url):
    return FALLBACK_IMAGES[zlib.adler32(url.encode("utf-8")) % len(FALLBACK_IMAGES)]

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
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))
    except Exception:
        return url.strip()

def source_name(url):
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
    domain = urlparse(url).netloc.replace("www.", "")
    return mapping.get(domain, domain or "Intelligence")

def detect_affected_model(text):
    low = text.lower()
    for model_name, identifiers in MODEL_SIGNATURES.items():
        if any(i in low for i in identifiers):
            return model_name
    return "General / Autonomous"

def assign_severity(sub_niche, text):
    low = text.lower()
    if any(w in low for w in ["cvss 10", "rce", "critical", "disaster", "root privilege", "breach"]):
        return {"level": "CRITICAL", "color": "#ff3b5c"}
    if sub_niche in ["Outage", "Jailbreak", "Security"]:
        return {"level": "HIGH", "color": "#f97316"}
    if sub_niche == "Hallucination":
        return {"level": "MODERATE", "color": "#eab308"}
    return {"level": "INFO", "color": "#00e5ff"}

def detect_sub_niche(title, summary, default_sub="General"):
    text = f"{title} {summary}".lower()
    if any(w in text for w in ["outage", "down", "offline", "crash", "blackout"]):
        return "Outage"
    if any(w in text for w in ["jailbreak", "injection", "override", "bypass"]):
        return "Jailbreak"
    if any(w in text for w in ["hallucinat", "wrong answer", "delusion"]):
        return "Hallucination"
    if any(w in text for w in ["exploit", "leak", "breach", "hack", "vulnerability"]):
        return "Security"
    if any(w in text for w in ["politics", "election", "government", "minister", "parliament"]):
        return "Politics"
    if any(w in text for w in ["gadget", "software", "app", "tech", "hardware", "device"]):
        return "Tech"
    return default_sub

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
            if total > 180_000 or b"</head>" in b"".join(chunks).lower():
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

            combined = f"{title} {summary}".lower()

            if section == "AI Failures":
                has_ai = any(term in combined for term in AI_KEYWORDS)
                has_failure = any(trigger in combined for trigger in AI_STRICT_FAILURES)
                if not (has_ai and has_failure):
                    continue

            sub_niche = detect_sub_niche(title, summary, default_sub)
            severity = assign_severity(sub_niche, combined)
            target_model = detect_affected_model(combined)

            articles.append({
                "title": title,
                "url": link,
                "section": section,
                "sub_niche": sub_niche,
                "source": source_name(link),
                "target_model": target_model,
                "severity": severity,
                "image_url": None,
                "summary": truncate(summary),
                "published": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
    except Exception as e:
        logging.error("Feed error %s: %s", feed_url, e)
    return articles

def check_ai_statuses():
    """Quick uptime check on AI operational endpoints."""
    endpoints = {
        "OpenAI": "https://status.openai.com/api/v2/status.json",
        "Anthropic": "https://status.anthropic.com/api/v2/status.json"
    }
    status_summary = {}
    for service, endpoint in endpoints.items():
        try:
            r = requests.get(endpoint, timeout=4)
            if r.status_code == 200:
                data = r.json()
                desc = data.get("status", {}).get("description", "Operational").lower()
                status_summary[service] = "Operational" if "all systems operational" in desc else "Incident Reported"
            else:
                status_summary[service] = "Unknown"
        except Exception:
            status_summary[service] = "Operational"
    return status_summary

def load_posted_cache():
    if not os.path.exists(POSTED_CACHE_FILE):
        return set()
    with open(POSTED_CACHE_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def mark_as_posted(url):
    with open(POSTED_CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(f"{url}\n")

def post_single_random_viral(articles):
    if not articles:
        return

    posted_urls = load_posted_cache()
    unposted = [a for a in articles if a["url"] not in posted_urls]
    if not unposted:
        logging.info("No new unposted articles available.")
        return

    # Prioritize high severity for breaking news
    critical_pool = [a for a in unposted if a["severity"]["level"] in ["CRITICAL", "HIGH"]]
    chosen = random.choice(critical_pool if critical_pool else unposted)

    # Payload formatted exactly as requested (Bold + Emoji, Title only, NO LINK)
    formatted_headline = f"🚨 **BREAKING NEWS** 🚨\n\n{chosen['title']}"

    payload = {
        "title": formatted_headline,
    }

    try:
        res = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code in (200, 202):
            mark_as_posted(chosen["url"])
            logging.info("[POSTED TO FACEBOOK] %s", chosen["title"])
    except Exception as e:
        logging.error("Webhook error: %s", e)

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
        return

    # Keep chronological order for freshness
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

    system_status = check_ai_statuses()
    output_data = {
        "statuses": system_status,
        "articles": articles
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logging.info("Complete! Saved %d items to %s", len(articles), OUTPUT_FILE)
    post_single_random_viral(articles)

if __name__ == "__main__":
    fetch_news()