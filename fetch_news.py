import os
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
CHECK_INTERVAL_SECONDS = 60  # Updates every 1 minute

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
    """Initializes SQLite database tables for structured article storage."""
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
    logging.info("Database initialized successfully.")

def is_article_exists(url):
    """Checks if an article is already saved in the database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM articles WHERE url = ?", (url,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def save_article(article):
    """Inserts a newly scraped article into the database."""
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
        pass  # Duplicate entry skipped safely
    except Exception as e:
        logging.error(f"Failed to insert article {article['url']}: {e}")
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Article Scraper & Meta Tag Extractor
# ---------------------------------------------------------------------------
def extract_article_metadata(article_url):
    """
    Extracts the exact primary reference image (og:image / twitter:image) 
    and verifies the meta tags of the source page.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    image_url = None
    
    try:
        response = requests.get(article_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Primary: OpenGraph image
            og_img = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'og:image'})
            if og_img and og_img.get('content'):
                image_url = og_img['content']
                
            # Secondary: Twitter card image
            if not image_url:
                tw_img = soup.find('meta', property='twitter:image') or soup.find('meta', attrs={'name': 'twitter:image'})
                if tw_img and tw_img.get('content'):
                    image_url = tw_img['content']
            
            # Tertiary: High-resolution img elements in article tags
            if not image_url:
                for img in soup.find_all('img'):
                    src = img.get('src', '')
                    if src.startswith('http') and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        image_url = src
                        break
    except requests.RequestException as req_err:
        logging.warning(f"Network error fetching metadata for {article_url}: {req_err}")
    except Exception as err:
        logging.error(f"Unexpected parsing error for {article_url}: {err}")
        
    return image_url

# ---------------------------------------------------------------------------
# Section Categorization & NLP Keyword Logic
# ---------------------------------------------------------------------------
def categorize_article(title, summary, source_category):
    """
    Maps content to strict site categories: AI Failures, Tech Failures, 
    Company Milestones, or General Tech.
    """
    text = f"{title} {summary}".lower()
    
    # 1. AI Failures priority check
    ai_fail_keywords = ['ai fail', 'hallucination', 'ai error', 'chatbot mistake', 'deepfake', 'llm glitch', 'openai bug']
    if any(k in text for k in ai_fail_keywords) or source_category == "AI_FAILURES":
        return "AI Failures"
        
    # 2. General Tech Failures check
    tech_fail_keywords = ['outage', 'data breach', 'down', 'hack', 'vulnerability', 'ddos', 'security flaw']
    if any(k in text for k in tech_fail_keywords) or source_category == "TECH_FAILURES":
        return "Tech Failures"
        
    # 3. Company Milestones check
    milestone_keywords = ['series a', 'series b', 'ipo', 'acquired', 'acquisition', 'record revenue', 'milestone', 'valuation']
    if any(k in text for k in milestone_keywords) or source_category == "COMPANY_MILESTONES":
        return "Company Milestones"
        
    # Default section fallback
    return "General Tech"

# ---------------------------------------------------------------------------
# Core Ingestion Loop
# ---------------------------------------------------------------------------
def process_feed_source(source_category, feed_url):
    """Parses individual feed sources and inserts new articles into database."""
    try:
        parsed_feed = feedparser.parse(feed_url)
        for entry in parsed_feed.entries[:10]:
            url = entry.get('link')
            if not url or is_article_exists(url):
                continue

            title = entry.get('title', 'Untitled News Article')
            summary = entry.get('summary', entry.get('description', ''))
            
            # Clean HTML tags out of summary
            if summary:
                summary = BeautifulSoup(summary, 'html.parser').get_text()

            section = categorize_article(title, summary, source_category)
            image_url = extract_article_metadata(url)
            published_str = entry.get('published', datetime.datetime.now(datetime.timezone.utc).isoformat())

            article_payload = {
                "title": title.strip(),
                "url": url.strip(),
                "section": section,
                "image_url": image_url,
                "summary": summary.strip()[:300] + '...' if len(summary) > 300 else summary.strip(),
                "language": "en",  # Metadata tag for frontend language selector
                "published": published_str
            }

            save_article(article_payload)
            
    except Exception as e:
        logging.error(f"Error processing RSS feed {feed_url}: {e}")

def run_fetch_cycle():
    """Executes a complete scanning cycle across all RSS sources."""
    logging.info("Starting automated fetch cycle...")
    for source_category, feeds in FEED_SOURCES.items():
        for feed_url in feeds:
            process_feed_source(source_category, feed_url)
    logging.info("Fetch cycle completed.")

def main():
    """Main daemon runner executing every 60 seconds."""
    init_db()
    logging.info("News Fetch Service started successfully.")
    
    while True:
        try:
            run_fetch_cycle()
        except KeyboardInterrupt:
            logging.info("Service manually stopped.")
            break
        except Exception as fatal_err:
            logging.critical(f"Unhandled service error: {fatal_err}")
            
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
