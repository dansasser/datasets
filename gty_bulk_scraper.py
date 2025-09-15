import os
import json
import time
import hashlib
import logging
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from tqdm import tqdm
import re

OUTPUT_FOLDER = "mvlm_comprehensive_dataset/gty_sermons"
LOG_FILENAME = "gty_sermons_scrape.log"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILENAME,
    filemode='a',
    format='[%(asctime)s] %(message)s',
    level=logging.INFO
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

def log(msg):
    print(msg)
    logging.info(msg)

def compute_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def already_downloaded(doc_hash):
    for fname in os.listdir(OUTPUT_FOLDER):
        if doc_hash in fname:
            return True
    return False

def save_sermon(text, meta):
    doc_hash = meta['hash'][:12]
    safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in meta['title'])[:60]
    base = f"{safe_title}_{doc_hash}"
    txt_path = os.path.join(OUTPUT_FOLDER, f"{base}.txt")
    json_path = os.path.join(OUTPUT_FOLDER, f"{base}.json")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

def extract_sermon_metadata(soup, transcript_text, url):
    title_el = soup.find("h1", class_="sermon-title")
    if title_el:
        title = title_el.get_text(strip=True)
    else:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True).replace("| Grace to You", "").strip()
        else:
            title = "Unknown Title"
    date_el = soup.find("div", class_="sermon-date")
    date = ""
    if date_el:
        date = date_el.get_text(strip=True)
    else:
        detail = soup.find("div", class_="sermon-detail-container")
        if detail:
            txt = detail.get_text(" ", strip=True)
            m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', txt)
            if m:
                date = m.group(0)
    scripture_el = soup.find("a", class_="sermon-scripture-link")
    scripture = scripture_el.get_text(strip=True) if scripture_el else ""
    word_count = len(transcript_text.split())
    doc_hash = compute_hash(transcript_text)
    return {
        "title": title,
        "date": date,
        "scripture": scripture,
        "url": url,
        "word_count": word_count,
        "hash": doc_hash
    }

def extract_full_transcript(page):
    try:
        if page.query_selector('.sermon-transcript-expand-btn'):
            page.click('.sermon-transcript-expand-btn')
            page.wait_for_timeout(600)
    except Exception:
        pass
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    transcript_container = soup.find('div', class_='sermon-detail-container')
    if transcript_container:
        transcript_paragraphs = transcript_container.find_all('p')
        transcript = "\n".join(p.get_text(strip=True) for p in transcript_paragraphs if p.get_text(strip=True))
    else:
        transcript_paragraphs = soup.find_all('p')
        transcript = "\n".join(p.get_text(strip=True) for p in transcript_paragraphs if p.get_text(strip=True))
    return transcript, soup

def get_all_sermon_links_ui():
    url = "https://www.gty.org/sermons/archive?tab=title"
    all_sermon_links = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_timeout(3000)
        soup = BeautifulSoup(page.content(), "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/sermons/") and "/archive" not in href:
                sermon_url = "https://www.gty.org" + href
                all_sermon_links.add(sermon_url)
        browser.close()
    return sorted(list(all_sermon_links))

def main(sequential=True):
    sermon_links = get_all_sermon_links_ui()
    log(f"Found {len(sermon_links)} sermon URLs. Starting download...")

    seen_urls = set()
    seen_hashes = set()

    if sequential:
        for idx, sermon_url in enumerate(tqdm(sermon_links, desc="Sermons")):
            if sermon_url in seen_urls:
                log(f"[{idx+1}/{len(sermon_links)}] Skipped duplicate URL: {sermon_url}")
                continue
            seen_urls.add(sermon_url)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                try:
                    page.goto(sermon_url, timeout=60000)
                    transcript, soup = extract_full_transcript(page)
                    if not transcript or len(transcript.split()) < 100:
                        log(f"NO TRANSCRIPT or too short for: {sermon_url}")
                        continue
                    meta = extract_sermon_metadata(soup, transcript, sermon_url)
                    if meta['hash'] in seen_hashes:
                        log(f"[{idx+1}/{len(sermon_links)}] Skipped duplicate content hash: {meta['title']}")
                        continue
                    seen_hashes.add(meta['hash'])
                    if already_downloaded(meta['hash']):
                        log(f"[{idx+1}/{len(sermon_links)}] Already downloaded: {meta['title']}")
                        continue
                    save_sermon(transcript, meta)
                    log(f"[{idx+1}/{len(sermon_links)}] Saved: {meta['title']} ({meta['date']}, {meta['word_count']} words)")
                    time.sleep(1)
                except PlaywrightTimeout:
                    log(f"[{idx+1}] TIMEOUT for: {sermon_url}")
                except Exception as e:
                    log(f"[{idx+1}] ERROR for: {sermon_url} -> {e}")
                finally:
                    browser.close()
    else:
        seen_urls = set()
        seen_hashes = set()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            for idx, sermon_url in enumerate(tqdm(sermon_links, desc="Sermons")):
                if sermon_url in seen_urls:
                    log(f"[{idx+1}/{len(sermon_links)}] Skipped duplicate URL: {sermon_url}")
                    continue
                seen_urls.add(sermon_url)
                try:
                    page.goto(sermon_url, timeout=60000)
                    transcript, soup = extract_full_transcript(page)
                    if not transcript or len(transcript.split()) < 100:
                        log(f"NO TRANSCRIPT or too short for: {sermon_url}")
                        continue
                    meta = extract_sermon_metadata(soup, transcript, sermon_url)
                    if meta['hash'] in seen_hashes:
                        log(f"[{idx+1}/{len(sermon_links)}] Skipped duplicate content hash: {meta['title']}")
                        continue
                    seen_hashes.add(meta['hash'])
                    if already_downloaded(meta['hash']):
                        log(f"[{idx+1}/{len(sermon_links)}] Already downloaded: {meta['title']}")
                        continue
                    save_sermon(transcript, meta)
                    log(f"[{idx+1}/{len(sermon_links)}] Saved: {meta['title']} ({meta['date']}, {meta['word_count']} words)")
                    time.sleep(1)
                except PlaywrightTimeout:
                    log(f"[{idx+1}] TIMEOUT for: {sermon_url}")
                except Exception as e:
                    log(f"[{idx+1}] ERROR for: {sermon_url} -> {e}")
            browser.close()
    log("Finished GTY bulk scrape.")

if __name__ == "__main__":
    use_sequential = True
    if "--batch" in sys.argv:
        use_sequential = False
    main(sequential=use_sequential)
