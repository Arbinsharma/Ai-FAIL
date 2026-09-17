import os
import re
import urllib.request
import feedparser
from bs4 import BeautifulSoup

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=artificial+intelligence+fails+or+mistakes&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
]

MAX_ARTICLES = 12

def clean_html(raw_html):
    """Remove HTML tags from text."""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

def get_real_url(google_url):
    """Follow Google News redirect to get the actual news site URL."""
    try:
        req = urllib.request.Request(
            google_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.geturl()
    except Exception:
        return google_url

def extract_meta_image(article_url):
    """Scrape the Open Graph meta image from the final source web page."""
    try:
        # Resolve real destination if coming from Google News
        if "news.google.com" in article_url:
            article_url = get_real_url(article_url)

        req = urllib.request.Request(
            article_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. Open Graph Meta Image
            og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
            if og_img and og_img.get("content"):
                img_src = og_img["content"]
                if img_src.startswith("http"):
                    return img_src

            # 2. Twitter Meta Image
            tw_img = soup.find("meta", property="twitter:image") or soup.find("meta", attrs={"name": "twitter:image"})
            if tw_img and tw_img.get("content"):
                img_src = tw_img["content"]
                if img_src.startswith("http"):
                    return img_src

            # 3. Direct Article Image Tag
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if src.startswith('http') and not src.endswith('.svg') and 'logo' not in src.lower():
                    return src
    except Exception as e:
        pass
    
    # Clean fallback if image cannot be extracted
    return "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80"

def fetch_all_news():
    """Fetch news items and extract true featured images."""
    articles = []
    seen_titles = set()

    for feed_url in RSS_FEEDS:
        if len(articles) >= MAX_ARTICLES:
            break
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            if len(articles) >= MAX_ARTICLES:
                break
            
            title = entry.get('title', 'No Title')
            if title in seen_titles:
                continue
            seen_titles.add(title)

            link = entry.get('link', '#')
            summary = clean_html(entry.get('summary', entry.get('description', 'No description available.')))
            
            print(f"Extracting image for: {title[:40]}...")
            image_url = extract_meta_image(link)
            source = entry.get('source', {}).get('title', 'AI News')

            articles.append({
                'title': title,
                'link': link,
                'summary': summary[:150] + '...' if len(summary) > 150 else summary,
                'image': image_url,
                'source': source
            })
    return articles

def generate_html(articles):
    """Generate modern, responsive HTML with smooth CSS transitions."""
    
    news_cards_html = ""
    for article in articles:
        news_cards_html += f"""
        <div class="news-card">
            <div class="card-img-container">
                <img src="{article['image']}" alt="News Image" loading="lazy" onerror="this.onerror=null; this.src='https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=800&q=80';">
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
    <title>AI Failed Portal - Live Updates</title>
    <style>
        :root {{
            --bg-color: #0b0e14;
            --card-bg: #131722;
            --text-color: #e6edf3;
            --text-muted: #8b949e;
            --accent-color: #3b82f6;
            --accent-hover: #60a5fa;
            --border-color: #21262d;
        }}

        [data-theme="light"] {{
            --bg-color: #f4f6f8;
            --card-bg: #ffffff;
            --text-color: #1f2937;
            --text-muted: #6b7280;
            --accent-color: #2563eb;
            --accent-hover: #1d4ed8;
            --border-color: #e5e7eb;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            transition: background-color 0.3s, color 0.3s, transform 0.3s ease, box-shadow 0.3s ease;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
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
            backdrop-filter: blur(10px);
        }}

        .navbar {{
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 1.5rem;
        }}

        .logo {{
            font-size: 1.4rem;
            font-weight: 800;
            color: var(--accent-color);
            letter-spacing: -0.5px;
        }}

        .nav-links {{
            display: flex;
            list-style: none;
            gap: 1.2rem;
            align-items: center;
        }}

        .nav-links a {{
            text-decoration: none;
            color: var(--text-color);
            font-weight: 500;
            font-size: 0.95rem;
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
            font-size: 0.85rem;
        }}

        .container {{
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1rem;
        }}

        .section {{
            margin-bottom: 3rem;
            animation: fadeIn 0.8s ease-in-out;
        }}

        h2.section-title {{
            font-size: 1.6rem;
            margin-bottom: 1.2rem;
            border-bottom: 3px solid var(--accent-color);
            display: inline-block;
            padding-bottom: 0.2rem;
        }}

        .news-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1.5rem;
        }}

        .news-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}

        .news-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.25);
        }}

        .card-img-container {{
            width: 100%;
            height: 190px;
            background-color: #111;
            overflow: hidden;
        }}

        .news-card img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.5s ease;
        }}

        .news-card:hover img {{
            transform: scale(1.05);
        }}

        .news-content {{
            padding: 1.2rem;
            display: flex;
            flex-direction: column;
            flex-grow: 1;
        }}

        .source-badge {{
            font-size: 0.7rem;
            background-color: var(--accent-color);
            color: #fff;
            padding: 0.2rem 0.6rem;
            border-radius: 12px;
            align-self: flex-start;
            margin-bottom: 0.6rem;
            font-weight: 600;
            text-transform: uppercase;
        }}

        .news-card h3 {{
            font-size: 1.05rem;
            margin-bottom: 0.6rem;
            line-height: 1.4;
        }}

        .news-card p {{
            color: var(--text-muted);
            font-size: 0.88rem;
            flex-grow: 1;
            margin-bottom: 1rem;
        }}

        .read-btn {{
            text-decoration: none;
            color: var(--accent-color);
            font-weight: 600;
            font-size: 0.88rem;
        }}

        .read-btn:hover {{
            color: var(--accent-hover);
        }}

        .about-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 2rem;
            border-radius: 12px;
        }}

        .gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
            gap: 1rem;
            margin-top: 1.2rem;
        }}

        .gallery img {{
            width: 100%;
            height: 130px;
            object-fit: cover;
            border-radius: 10px;
            border: 1px solid var(--border-color);
        }}

        .gallery img:hover {{
            transform: scale(1.03);
        }}

        footer {{
            text-align: center;
            padding: 2rem 1rem;
            border-top: 1px solid var(--border-color);
            background-color: var(--card-bg);
            margin-top: 3rem;
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @media (max-width: 600px) {{
            .navbar {{
                flex-direction: column;
                gap: 0.8rem;
                align-items: flex-start;
            }}
            .nav-links {{
                width: 100%;
                justify-content: space-between;
                font-size: 0.85rem;
            }}
            .news-grid {{
                grid-template-columns: 1fr;
            }}
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
            <p>Welcome to AI Failed Portal — automated tracking of real-time artificial intelligence mishaps, edge-case bugs, and breakthrough news from top global sources.</p>
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
                <p style="margin-top: 0.6rem;">Hello! I am Prashant Bhusal (Arbin Sharma), a Grade 9 student studying at <strong>Rosy Buds Bal Batika</strong> in Nepal. I am passionate about web development, programming, and automated web systems.</p>
                <p style="margin-top: 0.6rem;"><strong>AI Failed Portal</strong> automatically fetches and displays real-time updates regarding AI mishaps, technological advancements, and technical news coverage.</p>
                
                <h4 style="margin-top: 1.5rem;">Gallery</h4>
                <div class="gallery">
                    <img src="image1.jpg" alt="Gallery Image" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Profile+1';">
                    <img src="image2.jpg" alt="Gallery Image" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Profile+2';">
                    <img src="image3.jpg" alt="Gallery Image" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Profile+3';">
                    <img src="image4.jpg" alt="Gallery Image" onerror="this.onerror=null; this.src='https://via.placeholder.com/200?text=Profile+4';">
                </div>
            </div>
        </section>

        <section id="contact" class="section">
            <h2 class="section-title">Contact Me</h2>
            <div class="about-card">
                <p>Have questions or feedback? Feel free to write to me!</p>
                <p style="margin-top: 0.5rem;"><strong>Email:</strong> <a href="mailto:prashantvushal@gmail.com" style="color: var(--accent-color);">prashantvushal@gmail.com</a></p>
            </div>
        </section>
    </div>

    <footer>
        <p>&copy; 2026 AI Failed Portal. Developed by Prashant Bhusal (Arbin Sharma), Grade 9 Student at Rosy Buds Bal Batika.</p>
    </footer>

    <script>
        function toggleTheme() {{
            const body = document.body;
            if (body.getAttribute('data-theme') === 'light') {{
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
    print("Fetching news and extracting images...")
    news_items = fetch_all_news()
    print(f"Successfully processed {len(news_items)} news items.")
    generate_html(news_items)
    print("Successfully generated index.html!")
