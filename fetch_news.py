import os
import sys
import time
import logging
import sqlite3
import datetime
import requests
from bs4 import BeautifulSoup
import feedparser

# ---------------------------------------------------------------------------
# Configuration & Setup
# ---------------------------------------------------------------------------
DB_NAME = "news_portal.db"
CHECK_INTERVAL_SECONDS = 300  # Default: Check every 5 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("fetch_news.log"),
        logging.StreamHandler()
    ]
)

FEED_SOURCES = {
    "AI_FAILURES": [
        "https://hnrss.org/newest?q=AI+failure",
        "https://hnrss.org/newest?q=AI+mistake",
        "https://hnrss.org/newest?q=hallucination+AI",
    ],
    "TECH_FAILURES": [
        "https://hnrss.org/newest?q=outage",
        "https://hnrss.org/newest?q=data+breach",
        "https://hnrss.org/newest?q=cyberattack",
    ],
    "COMPANY_MILESTONES": [
        "https://hnrss.org/newest?q=acquisition",
        "https://hnrss.org/newest?q=IPO",
        "https://hnrss.org/newest?q=funding+round",
        "https://hnrss.org/newest?q=breakthrough",
    ],
    "GENERAL_TECH": [
        "https://news.ycombinator.com/rss",
        "https://www.cio.com/feed/",
    ]
}

# ---------------------------------------------------------------------------
# Database Management
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            section TEXT NOT NULL,
            image_url TEXT,
            summary TEXT,
            language TEXT DEFAULT 'en',
            published_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def is_article_exists(url):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM articles WHERE url = ?", (url,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def save_article(article):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO articles (title, url, section, image_url, summary, language, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            article['title'],
            article['url'],
            article['section'],
            article['image_url'],
            article['summary'],
            article['language'],
            article['published']
        ))
        conn.commit()
        logging.info(f"Saved new article: {article['title'][:40]}... -> [{article['section']}]")
    except sqlite3.IntegrityError:
        pass
    except Exception as e:
        logging.error(f"Failed to insert article {article['url']}: {e}")
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Scraper & Metadata Extractor
# ---------------------------------------------------------------------------
def extract_article_metadata(article_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    image_url = None
    try:
        response = requests.get(article_url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            og_img = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'og:image'})
            if og_img and og_img.get('content'):
                image_url = og_img['content']
            if not image_url:
                tw_img = soup.find('meta', property='twitter:image') or soup.find('meta', attrs={'name': 'twitter:image'})
                if tw_img and tw_img.get('content'):
                    image_url = tw_img['content']
    except Exception:
        pass
    return image_url

def categorize_article(title, summary, source_category):
    text = f"{title} {summary}".lower()
    if any(k in text for k in ['ai fail', 'hallucination', 'ai error', 'chatbot mistake', 'deepfake']) or source_category == "AI_FAILURES":
        return "AI Failures"
    if any(k in text for k in ['outage', 'data breach', 'down', 'hack', 'vulnerability']) or source_category == "TECH_FAILURES":
        return "Tech Failures"
    if any(k in text for k in ['series a', 'ipo', 'acquired', 'acquisition', 'milestone']) or source_category == "COMPANY_MILESTONES":
        return "Company Milestones"
    return "General Tech"

# ---------------------------------------------------------------------------
# Fetch Operations
# ---------------------------------------------------------------------------
def run_fetch_cycle():
    logging.info("Starting automated fetch cycle...")
    for source_category, feeds in FEED_SOURCES.items():
        for feed_url in feeds:
            try:
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries[:5]:
                    url = entry.get('link')
                    if not url or is_article_exists(url):
                        continue
                    
                    title = entry.get('title', 'Untitled')
                    summary = entry.get('summary', '')
                    if summary:
                        summary = BeautifulSoup(summary, 'html.parser').get_text()

                    section = categorize_article(title, summary, source_category)
                    image_url = extract_article_metadata(url)
                    
                    save_article({
                        "title": title.strip(),
                        "url": url.strip(),
                        "section": section,
                        "image_url": image_url,
                        "summary": summary.strip()[:300],
                        "language": "en",
                        "published": entry.get('published', datetime.datetime.now(datetime.timezone.utc).isoformat())
                    })
            except Exception as e:
                logging.error(f"Feed error {feed_url}: {e}")
    logging.info("Fetch cycle completed.")

def main():
    init_db()
    
    # Check if run with --once argument
    if "--once" in sys.argv:
        logging.info("Running single fetch cycle (--once mode)...")
        run_fetch_cycle()
        logging.info("Done! Exiting script.")
        sys.exit(0)
    
    # Standard daemon loop mode (5-minute interval)
    logging.info("Starting continuous loop mode (5-minute interval)...")
    while True:
        try:
            run_fetch_cycle()
        except KeyboardInterrupt:
            break
        except Exception as err:
            logging.error(f"Loop error: {err}")
        
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
