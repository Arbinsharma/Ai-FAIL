import json
import logging
import datetime
import html as html_lib
import re
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
# FALLBACK IMAGE
# ============================================================

FALLBACK_IMG = (
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe"
    "?auto=format&fit=crop&w=1200&q=80"
)


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
    "failure": 8,
    "failed": 8,
    "fails": 8,
    "crash": 7,
    "crashed": 7,
    "error": 6,
    "wrong": 4,
    "incorrect": 5,
    "hallucination": 10,
    "hallucinated": 10,
    "misinformation": 7,
    "misleading": 5,
    "bug": 6,
    "broken": 7,
    "malfunction": 8,
    "glitch": 6,
    "problem": 4,
}

SECURITY_WORDS = {
    "security": 8,
    "hack": 8,
    "hacked": 9,
    "attack": 7,
    "vulnerability": 10,
    "vulnerable": 8,
    "exploit": 10,
    "jailbreak": 10,
    "prompt injection": 12,
    "data leak": 12,
    "breach": 12,
    "malware": 10,
    "phishing": 8,
}

OUTAGE_WORDS = {
    "outage": 12,
    "down": 8,
    "downtime": 10,
    "offline": 8,
    "unavailable": 9,
    "service disruption": 10,
    "disruption": 8,
    "server issue": 8,
}

MILESTONE_WORDS = {
    "launch": 6,
    "launched": 6,
    "release": 6,
    "released": 6,
    "funding": 8,
    "raised": 7,
    "valuation": 8,
    "acquisition": 9,
    "acquired": 9,
    "partnership": 6,
    "million": 5,
    "billion": 7,
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
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def truncate(text, length=220):
    text = text.strip()

    if len(text) <= length:
        return text

    shortened = text[:length - 3].rsplit(" ", 1)[0]
    return shortened + "..."


def normalize_url(url):
    return url.strip().split("#")[0]


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

    for word, value in FAILURE_WORDS.items():
        if word in text:
            score += value

    for word, value in SECURITY_WORDS.items():
        if word in text:
            score += value

    for word, value in OUTAGE_WORDS.items():
        if word in text:
            score += value

    for word, value in MILESTONE_WORDS.items():
        if word in text:
            score += value

    return score


# ============================================================
# INCIDENT TYPE
# ============================================================

def detect_incident_type(title, summary, section):
    text = f"{title} {summary}".lower()

    if any(word in text for word in OUTAGE_WORDS):
        return "Outage"

    if any(word in text for word in SECURITY_WORDS):
        return "Security"

    if any(word in text for word in FAILURE_WORDS):
        return "Failure"

    if section == "Company Milestones":
        return "Milestone"

    return "News"


# ============================================================
# STATUS
# ============================================================

def detect_status(title, summary):
    text = f"{title} {summary}".lower()

    confirmed_words = [
        "confirmed",
        "official",
        "investigation found",
        "company said",
        "company confirmed",
    ]

    reported_words = [
        "reported",
        "reports",
        "according to",
        "may have",
        "appears to",
        "users say",
    ]

    if any(word in text for word in confirmed_words):
        return "Confirmed"

    if any(word in text for word in reported_words):
        return "Reported"

    return "Reported"


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_og_image(article_url):
    try:
        response = requests.get(
            article_url,
            headers=HEADERS,
            timeout=7,
            stream=True
        )

        if response.status_code != 200:
            return None

        data = b""

        for chunk in response.iter_content(8192):
            data += chunk

            if b"</head>" in data.lower():
                break

            if len(data) > 150_000:
                break

        soup = BeautifulSoup(data, "html.parser")

        image_properties = [
            ("property", "og:image"),
            ("property", "og:image:secure_url"),
            ("name", "twitter:image"),
            ("name", "twitter:image:src"),
        ]

        for attr, value in image_properties:
            tag = soup.find("meta", attrs={attr: value})

            if tag and tag.get("content"):
                image = tag["content"].strip()

                if image.startswith("http"):
                    return image

        image = soup.find("img")

        if image:
            src = image.get("src", "")

            if src.startswith("http"):
                return src

    except Exception as error:
        logging.debug(
            "Image extraction failed for %s: %s",
            article_url,
            error
        )

    return None


# ============================================================
# FETCH RSS
# ============================================================

def fetch_feed(feed_url, section):
    articles = []

    try:
        logging.info("Reading %s", feed_url)

        feed = feedparser.parse(feed_url)

        if getattr(feed, "bozo", False):
            logging.warning(
                "Feed warning: %s",
                feed_url
            )

        for entry in feed.entries[:10]:

            link = normalize_url(
                entry.get("link", "")
            )

            if not link:
                continue

            # Skip Hacker News discussion pages
            if "news.ycombinator.com/item" in link:
                continue

            title = clean_html(
                entry.get("title", "Untitled")
            )

            summary = clean_html(
                entry.get("summary")
                or entry.get("description")
                or ""
            )

            if not title:
                continue

            score = calculate_score(
                title,
                summary
            )

            articles.append({
                "title": title,
                "url": link,
                "section": section,
                "incident_type": detect_incident_type(
                    title,
                    summary,
                    section
                ),
                "source": source_name(link),
                "image_url": None,
                "summary": truncate(summary),
                "published": to_iso(entry),
                "score": score,
                "status": detect_status(
                    title,
                    summary
                ),
            })

    except Exception as error:
        logging.error(
            "Feed error %s: %s",
            feed_url,
            error
        )

    return articles


# ============================================================
# MAIN FETCH
# ============================================================

def fetch_news():

    logging.info("=" * 60)
    logging.info("AIFAIL NEWS ENGINE STARTING")
    logging.info("=" * 60)

    articles = []
    seen_urls = set()

    # --------------------------------------------------------
    # Fetch RSS feeds concurrently
    # --------------------------------------------------------

    tasks = []

    with ThreadPoolExecutor(max_workers=8) as executor:

        for section, feeds in FEED_SOURCES.items():

            for feed_url in feeds:

                tasks.append(
                    executor.submit(
                        fetch_feed,
                        feed_url,
                        section
                    )
                )

        for task in as_completed(tasks):

            try:
                results = task.result()

                for article in results:

                    url = article["url"]

                    if url in seen_urls:
                        continue

                    seen_urls.add(url)
                    articles.append(article)

            except Exception as error:
                logging.error(
                    "Worker error: %s",
                    error
                )

    if not articles:
        logging.error(
            "No articles were collected."
        )
        return

    logging.info(
        "Collected %d unique articles.",
        len(articles)
    )

    # --------------------------------------------------------
    # Get article images
    # --------------------------------------------------------

    logging.info(
        "Finding article images..."
    )

    with ThreadPoolExecutor(max_workers=10) as executor:

        future_map = {
            executor.submit(
                extract_og_image,
                article["url"]
            ): article
            for article in articles
        }

        for future in as_completed(future_map):

            article = future_map[future]

            try:
                image = future.result()

                article["image_url"] = (
                    image
                    if image
                    else FALLBACK_IMG
                )

            except Exception:
                article["image_url"] = FALLBACK_IMG

    # --------------------------------------------------------
    # Sort newest first
    # --------------------------------------------------------

    articles.sort(
        key=lambda article: (
            article.get("published", ""),
            article.get("score", 0)
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # Keep site reasonably fast
    # --------------------------------------------------------

    articles = articles[:80]

    # --------------------------------------------------------
    # Add ranking number
    # --------------------------------------------------------

    for index, article in enumerate(
        articles,
        start=1
    ):
        article["rank"] = index

    # --------------------------------------------------------
    # Save JSON
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            articles,
            file,
            indent=2,
            ensure_ascii=False
        )

    logging.info(
        "Saved %d articles to %s",
        len(articles),
        OUTPUT_FILE
    )

    logging.info("=" * 60)
    logging.info("AIFAIL NEWS ENGINE FINISHED")
    logging.info("=" * 60)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    fetch_news()