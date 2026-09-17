import os
import json
import logging
import datetime
import requests
from bs4 import BeautifulSoup
import feedparser

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

JSON_FILE = "articles.json"

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

def extract_article_metadata(article_url):
    """Scrapes the reference article directly to get the real cover image."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    image_url = None
    try:
        response = requests.get(article_url, headers=headers, timeout=6)
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

def run_fetch():
    logging.info("Fetching latest news...")
    articles = []
    seen_urls = set()

    for source_category, feeds in FEED_SOURCES.items():
        for feed_url in feeds:
            try:
                parsed = feedparser.parse(feed_url)
                for entry in parsed.entries[:5]:
                    url = entry.get('link')
                    if not url or url in seen_urls:
                        continue
                    
                    title = entry.get('title', 'Untitled')
                    summary = entry.get('summary', '')
                    if summary:
                        summary = BeautifulSoup(summary, 'html.parser').get_text()

                    section = categorize_article(title, summary, source_category)
                    image_url = extract_article_metadata(url)
                    
                    articles.append({
                        "title": title.strip(),
                        "url": url.strip(),
                        "section": section,
                        "image_url": image_url,
                        "summary": summary.strip()[:250] + '...' if len(summary) > 250 else summary.strip(),
                        "language": "en",
                        "published": entry.get('published', datetime.datetime.now(datetime.timezone.utc).isoformat())
                    })
                    seen_urls.add(url)
            except Exception as e:
                logging.error(f"Error fetching feed {feed_url}: {e}")

    # Write directly to JSON for your frontend website to read
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)
        
    logging.info(f"Successfully saved {len(articles)} articles to {JSON_FILE}!")

if __name__ == "__main__":
    run_fetch()
