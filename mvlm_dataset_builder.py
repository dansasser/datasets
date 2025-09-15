import requests
from bs4 import BeautifulSoup
import os
import time
import json

BASE_URL = "https://www.gty.org/library/sermons"
OUTPUT_FOLDER = "gty_sermons"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def get_sermon_links(page_url):
    res = requests.get(page_url, timeout=20)
    soup = BeautifulSoup(res.text, "html.parser")
    links = []
    for a in soup.select("a.sermon-title-link"):
        href = a['href']
        if href.startswith("/library/sermons/"):
            links.append("https://www.gty.org" + href)
    return links

def get_next_page(soup):
    next_a = soup.find("a", {"aria-label": "Next Page"})
    if next_a and next_a.get("href"):
        return "https://www.gty.org" + next_a.get("href")
    return None

def fetch_and_save_sermon(url):
    r = requests.get(url, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.find("h1", class_="sermon-title").text.strip()
    series = soup.find("a", class_="sermon-series-link")
    series = series.text.strip() if series else ""
    date = soup.find("time")
    date = date.text.strip() if date else ""
    body = soup.find("div", class_="sermon-transcript-body")
    transcript = body.get_text(separator="\n", strip=True) if body else ""
    if not transcript:
        print(f"NO TRANSCRIPT: {url}")
        return
    meta = {
        "title": title,
        "series": series,
        "date": date,
        "url": url,
        "word_count": len(transcript.split())
    }
    safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in title)[:60]
    base = f"{safe_title}_{meta['date'].replace(' ', '_')}".replace('__', '_')
    with open(os.path.join(OUTPUT_FOLDER, f"{base}.txt"), "w", encoding="utf-8") as f:
        f.write(transcript)
    with open(os.path.join(OUTPUT_FOLDER, f"{base}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"Saved: {meta['title']}")

def main():
    url = BASE_URL
    seen = set()
    page_num = 1
    while url and page_num < 100:
        print(f"Scraping page: {url}")
        res = requests.get(url, timeout=20)
        soup = BeautifulSoup(res.text, "html.parser")
        links = get_sermon_links(url)
        for sermon_url in links:
            if sermon_url not in seen:
                seen.add(sermon_url)
                fetch_and_save_sermon(sermon_url)
                time.sleep(2)  # Be respectful!
        url = get_next_page(soup)
        page_num += 1

    print("Done.")

if __name__ == "__main__":
    main()
