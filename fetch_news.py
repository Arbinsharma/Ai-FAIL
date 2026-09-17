import os
import re
import urllib.parse
import feedparser

# RSS Feeds for AI News & Failures/Updates
RSS_FEEDS = [
    "https://news.google.com/rss/search?q=artificial+intelligence+fails+or+mistakes&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
]

MAX_ARTICLES = 12  # Limits articles so the page loads fast without endless scrolling

def clean_html(raw_html):
    """Remove HTML tags from text."""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

def extract_image(entry):
    """Extract an image URL from an RSS entry if available."""
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0].get('url', '')
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0].get('url', '')
    if 'links' in entry:
        for link in entry.links:
            if link.get('type', '').startswith('image/'):
                return link.get('href', '')
    # Default SVG placeholder fallback
    return "https://via.placeholder.com/600x350/1e1e1e/4da6ff?text=AI+Failed+Portal"

def fetch_all_news():
    """Fetch news items from RSS feeds up to MAX_ARTICLES."""
    articles = []
    seen_titles = set()

    for url in RSS_FEEDS:
        if len(articles) >= MAX_ARTICLES:
            break
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if len(articles) >= MAX_ARTICLES:
                break
            title = entry.get('title', 'No Title')
            if title in seen_titles:
                continue
            seen_titles.add(title)

            link = entry.get('link', '#')
            summary = clean_html(entry.get('summary', entry.get('description', 'No description available.')))
            image_url = extract_image(entry)
            source = entry.get('source', {}).get('title', 'AI News Source')

            articles.append({
                'title': title,
                'link': link,
                'summary': summary[:160] + '...' if len(summary) > 160 else summary,
                'image': image_url,
                'source': source
            })
    return articles

def generate_html(articles):
    """Generate the full HTML page."""
    
    news_cards_html = ""
    for article in articles:
        news_cards_html += f"""
        <div class="news-card">
            <div class="card-img-container">
                <img src="{article['image']}" alt="News Image" onerror="this.onerror=null; this.src='https://via.placeholder.com/600x350/1e1e1e/4da6ff?text=AI+Failed+Portal';">
            </div>
            <div class="news-content">
                <span class="source-badge">{article['source']}</span>
                <h3>{article['title']}</h3>
                <p>{article['summary']}</p>
                <a href="{article['link']}" target="_blank" class="read-btn">Read Reference Article &rarr;</a>
            </div>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Failed Portal - Latest AI Failures & News</title>
    <style>
        :root {{
            --bg-color: #0d1117;
            --card-bg: #161b22;
            --text-color: #c9d1d9;
            --text-muted: #8b949e;
            --accent-color: #58a6ff;
            --border-color: #30363d;
        }}

        [data-theme="light"] {{
            --bg-color: #f6f8fa;
            --card-bg: #ffffff;
            --text-color: #24292f;
            --text-muted: #57606a;
            --accent-color: #0969da;
            --border-color: #d0d7de;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            transition: background-color 0.3s, color 0.3s;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
        }}

        header {{
            background-color: var(--card-bg);
            border-bottom: 1px solid var(--border-color);
            position: sticky;
            top: 0;
            z-index: 1000;
        }}

        .navbar {{
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 2rem;
        }}

        .logo {{
            font-size: 1.5rem;
            font-weight: bold;
            color: var(--accent-color);
        }}

        .nav-links {{
            display: flex;
            list-style: none;
            gap: 1.5rem;
            align-items: center;
        }}

        .nav-links a {{
            text-decoration: none;
            color: var(--text-color);
            font-weight: 500;
        }}

        .nav-links a:hover {{
            color: var(--accent-color);
        }}

        .theme-btn {{
            background: none;
            border: 1px solid var(--border-color);
            color: var(--text-color);
            padding: 0.4rem 0.8rem;
            border-radius: 20px;
            cursor: pointer;
        }}

        .container {{
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1.5rem;
        }}

        .section {{
            margin-bottom: 3rem;
        }}

        h2.section-title {{
            font-size: 1.8rem;
            margin-bottom: 1.5rem;
            border-bottom: 2px solid var(--accent-color);
            display: inline-block;
            padding-bottom: 0.3rem;
        }}

        .news-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 1.8rem;
        }}

        .news-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}

        .card-img-container {{
            width: 100%;
            height: 200px;
            background-color: #000;
            overflow: hidden;
        }}

        .news-card img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        .news-content {{
            padding: 1.2rem;
            display: flex;
            flex-direction: column;
            flex-grow: 1;
        }}

        .source-badge {{
            font-size: 0.75rem;
            background-color: var(--accent-color);
            color: #fff;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            align-self: flex-start;
            margin-bottom: 0.5rem;
        }}

        .news-card h3 {{
            font-size: 1.1rem;
            margin-bottom: 0.5rem;
        }}

        .news-card p {{
            color: var(--text-muted);
            font-size: 0.9rem;
            flex-grow: 1;
            margin-bottom: 1rem;
        }}

        .read-btn {{
            text-decoration: none;
            color: var(--accent-color);
            font-weight: bold;
            font-size: 0.9rem;
        }}

        .about-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 2rem;
            border-radius: 10px;
        }}

        .gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 1rem;
            margin-top: 1.5rem;
        }}

        .gallery img {{
            width: 100%;
            height: 160px;
            object-fit: cover;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}

        footer {{
            text-align: center;
            padding: 2rem;
            border-top: 1px solid var(--border-color);
            background-color: var(--card-bg);
            margin-top: 3rem;
        }}
    </style>
</head>
<body>

    <header>
        <nav class="navbar">
            <div class="logo">AI Failed Portal</div>
            <ul class="nav-links">
                <li><a href="#home">Home</a></li>
                <li><a href="#news">AI News</a></li>
                <li><a href="#about">About</a></li>
                <li><a href="#contact">Contact</a></li>
                <li><button class="theme-btn" onclick="toggleTheme()">🌓 Theme</button></li>
            </ul>
        </nav>
    </header>

    <div class="container">
        <section id="home" class="section">
            <h2 class="section-title">Latest AI Failures & Updates</h2>
            <p>Welcome to AI Failed Portal — real-time automated tracking of artificial intelligence mishaps, errors, and breaking news from global sources.</p>
        </section>

        <section id="news" class="section">
            <h2 class="section-title">AI News Feed</h2>
            <div class="news-grid">
                {news_cards_html}
            </div>
        </section>

        <section id="about" class="section">
            <h2 class="section-title">About the Developer</h2>
            <div class="about-card">
                <h3>Prashant Bhusal / Arbin Sharma</h3>
                <p style="margin-top: 0.5rem;">Hello! I am Prashant Bhusal (also known as Arbin Sharma), a 9th-grade student studying at Rose Buds Balvatika School in Nepal. I am a tech enthusiast focused on web development, automation, and cybersecurity.</p>
                <p style="margin-top: 0.5rem;">I created <strong>AI Failed Portal</strong> to automatically fetch and curate real-time intelligence on artificial intelligence failures, glitches, and major breakthroughs across the tech industry.</p>
                
                <h4 style="margin-top: 1.5rem;">Gallery</h4>
                <div class="gallery">
                    <img src="image1.jpg" alt="Photo 1" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Photo+1';">
                    <img src="image2.jpg" alt="Photo 2" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Photo+2';">
                    <img src="image3.jpg" alt="Photo 3" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Photo+3';">
                    <img src="image4.jpg" alt="Photo 4" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Photo+4';">
                    <img src="image5.jpg" alt="Photo 5" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Photo+5';">
                </div>
            </div>
        </section>

        <section id="contact" class="section">
            <h2 class="section-title">Contact Me</h2>
            <div class="about-card">
                <p>Have suggestions or feedback? Reach out directly via email!</p>
                <p style="margin-top: 0.5rem;"><strong>Email:</strong> <a href="mailto:prashantvushal@gmail.com" style="color: var(--accent-color);">prashantvushal@gmail.com</a></p>
            </div>
        </section>
    </div>

    <footer>
        <p>&copy; 2026 AI Failed Portal. Developed by Prashant Bhusal (Arbin Sharma), 9th Grade Student at Rose Buds Balvatika.</p>
    </footer>

    <script>
        function toggleTheme() {{
            const body = document.body;
            const currentTheme = body.getAttribute('data-theme');
            if (currentTheme === 'light') {{
                body.removeAttribute('data-theme');
            }} else {{
                body.setAttribute('data-theme', 'light');
            }}
        }}
    </script>
</body>
</html>
"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

if __name__ == "__main__":
    print("Fetching news...")
    news_items = fetch_all_news()
    print(f"Fetched {len(news_items)} news items.")
    generate_html(news_items)
    print("Successfully generated index.html!")
