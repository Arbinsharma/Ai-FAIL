import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Fetch latest AI safety / failure news via Google News RSS
QUERY = "AI safety OR AI prompt jailbreak OR ChatGPT limitation OR AI vulnerability"
encoded_query = urllib.parse.quote(QUERY)
url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

try:
    with urllib.request.urlopen(req) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)
    items = root.findall(".//item")[:5]  # Top 5 news items

    news_list = []
    for item in items:
        title = item.find("title").text if item.find("title") is not None else ""
        link = item.find("link").text if item.find("link") is not None else ""
        news_list.append(f"<li><a href='{link}' target='_blank'>{title}</a></li>")

    news_html = "\n".join(news_list)
except Exception as e:
    news_html = f"<li>Could not fetch news today: {e}</li>"

# HTML Template
html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Watchdog & Safety Updates</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            padding-bottom: 20px;
            border-bottom: 2px solid #334155;
        }}
        h1 {{
            color: #38bdf8;
            font-size: 2.5rem;
        }}
        .badge {{
            background-color: #ef4444;
            color: white;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.875rem;
            text-transform: uppercase;
            font-weight: bold;
        }}
        .card {{
            background-color: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 24px;
            margin-top: 30px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        ul {{
            list-style: none;
            padding: 0;
        }}
        li {{
            background: #0f172a;
            margin: 12px 0;
            padding: 16px;
            border-radius: 6px;
            border-left: 4px solid #ef4444;
        }}
        a {{
            color: #38bdf8;
            text-decoration: none;
            font-size: 1.1rem;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        footer {{
            margin-top: 40px;
            text-align: center;
            color: #94a3b8;
            font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>AI Threat & Vulnerability Tracker</h1>
            <p>Automatically capturing AI failures, jailbreaks, and safety risks.</p>
        </header>
        
        <div class="card">
            <h2><span class="badge">Latest Incidents</span> Automated Feed</h2>
            <ul>
                {news_html}
            </ul>
        </div>

        <footer>
            <p>Last updated on: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
        </footer>
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("index.html updated successfully!")
