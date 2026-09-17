import os
import re
import urllib.parse
import feedparser

# RSS Feeds for AI News
RSS_FEEDS = [
    "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
]

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
    # Fallback default image
    return "https://via.placeholder.com/600x350?text=AI+News"

def fetch_all_news():
    """Fetch news items from RSS feeds."""
    articles = []
    seen_titles = set()

    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries:
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
                'summary': summary[:200] + '...' if len(summary) > 200 else summary,
                'image': image_url,
                'source': source
            })
    return articles

def generate_html(articles):
    """Generate the full HTML page."""
    
    # Generate news grid cards
    news_cards_html = ""
    for article in articles:
        news_cards_html += f"""
        <div class="news-card">
            <img src="{article['image']}" alt="News Image" onerror="this.src='https://via.placeholder.com/600x350?text=AI+News';">
            <div class="news-content">
                <span class="source-badge">{article['source']}</span>
                <h3>{article['title']}</h3>
                <p>{article['summary']}</p>
                <a href="{article['link']}" target="_blank" class="read-btn">Read Reference Article &rarr;</a>
            </div>
        </div>
        """

    # Full HTML structure
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Pulse - Latest AI News</title>
    <style>
        :root {{
            --bg-color: #f4f6f9;
            --card-bg: #ffffff;
            --text-color: #1a1a1a;
            --text-muted: #666666;
            --accent-color: #0066cc;
            --border-color: #e0e0e0;
        }}

        [data-theme="dark"] {{
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e0e0e0;
            --text-muted: #aaa;
            --accent-color: #4da6ff;
            --border-color: #333333;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            transition: background-color 0.3s, color 0.3s;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
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
            font-size: 2rem;
            margin-bottom: 1.5rem;
            border-bottom: 2px solid var(--accent-color);
            display: inline-block;
            padding-bottom: 0.3rem;
        }}

        /* News Grid */
        .news-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 2rem;
        }}

        .news-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}

        .news-card img {{
            width: 100%;
            height: 200px;
            object-fit: cover;
        }}

        .news-content {{
            padding: 1.2rem;
            display: flex;
            flex-direction: column;
            flex-grow: 1;
        }}

        .source-badge {{
            font-size: 0.8rem;
            background-color: var(--accent-color);
            color: #fff;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            align-self: flex-start;
            margin-bottom: 0.5rem;
        }}

        .news-card h3 {{
            font-size: 1.2rem;
            margin-bottom: 0.5rem;
        }}

        .news-card p {{
            color: var(--text-muted);
            font-size: 0.95rem;
            flex-grow: 1;
            margin-bottom: 1rem;
        }}

        .read-btn {{
            text-decoration: none;
            color: var(--accent-color);
            font-weight: bold;
        }}

        /* About & Gallery */
        .about-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 2rem;
            border-radius: 8px;
        }}

        .gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 1rem;
            margin-top: 1.5rem;
        }}

        .gallery img {{
            width: 100%;
            height: 180px;
            object-fit: cover;
            border-radius: 6px;
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
            <div class="logo">AI Pulse Portal</div>
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
        <!-- Home Section -->
        <section id="home" class="section">
            <h2 class="section-title">Latest AI Updates</h2>
            <p>Welcome to AI Pulse, your automated news portal for real-time artificial intelligence updates.</p>
        </section>

        <!-- News Section -->
        <section id="news" class="section">
            <h2 class="section-title">AI News Feed</h2>
            <div class="news-grid">
                {news_cards_html}
            </div>
        </section>

        <!-- About Section -->
        <section id="about" class="section">
            <h2 class="section-title">About the Developer</h2>
            <div class="about-card">
                <h3>Prashant Bhusal / Arbin Sharma</h3>
                <p>Hi! I am Prashant Bhusal (Arbin Sharma), a 9th-grade student at Rose Buds Balvatika in Nepal. I built this automated AI news portal to track real-time artificial intelligence developments from top global sources.</p>
                
                <h4 style="margin-top: 1.5rem;">Gallery</h4>
                <div class="gallery">
                    <img src="image1.jpg" alt="Prashant Bhusal 1" onerror="this.src='https://via.placeholder.com/200?text=Photo+1';">
                    <img src="image2.jpg" alt="Prashant Bhusal 2" onerror="this.src='https://via.placeholder.com/200?text=Photo+2';">
                    <img src="image3.jpg" alt="Prashant Bhusal 3" onerror="this.src='https://via.placeholder.com/200?text=Photo+3';">
                    <img src="image4.jpg" alt="Prashant Bhusal 4" onerror="this.src='https://via.placeholder.com/200?text=Photo+4';">
                    <img src="image5.jpg" alt="Prashant Bhusal 5" onerror="this.src='https://via.placeholder.com/200?text=Photo+5';">
                </div>
            </div>
        </section>

        <!-- Contact Section -->
        <section id="contact" class="section">
            <h2 class="section-title">Contact Me</h2>
            <div class="about-card">
                <p>Have suggestions or feedback? Reach out directly via email!</p>
                <p style="margin-top: 0.5rem;"><strong>Email:</strong> <a href="mailto:your_email@example.com" style="color: var(--accent-color);">your_email@example.com</a></p>
            </div>
        </section>
    </div>

    <footer>
        <p>&copy; 2026 AI Pulse Portal. Developed by Prashant Bhusal (Arbin Sharma).</p>
    </footer>

    <script>
        function toggleTheme() {{
            const body = document.body;
            const currentTheme = body.getAttribute('data-theme');
            if (currentTheme === 'dark') {{
                body.removeAttribute('data-theme');
            }} else {{
                body.setAttribute('data-theme', 'dark');
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
