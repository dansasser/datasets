import os
import json
import time
import hashlib
import logging
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from tqdm import tqdm

OUTPUT_FOLDER = "intouch_articles_dataset"
LOG_FILENAME = "intouch_articles_scrape.log"
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

def save_article(text, meta):
    doc_hash = meta['hash'][:12]
    safe_title = "".join(c if c.isalnum() or c in "_-" else "_" for c in meta['title'])[:60]
    base = f"{safe_title}_{doc_hash}"
    txt_path = os.path.join(OUTPUT_FOLDER, f"{base}.txt")
    json_path = os.path.join(OUTPUT_FOLDER, f"{base}.json")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

def extract_full_article(page):
    try:
        page.wait_for_selector("main h1, main", timeout=10000)
        main_text = page.inner_text("main")
    except Exception:
        main_text = ""
    lines = [l.strip() for l in main_text.split("\n") if l.strip()]
    if not lines or len(lines) < 3:
        return "", {"title": "", "date": "", "author": ""}
    # Find the marking and get true title
    idx = 0
    if lines[idx] in ("FEATURE ARTICLE", "DAILY DEVOTION"):
        idx += 1
    title = lines[idx]
    idx += 1
    # Optionally skip Markdown underline or blank line
    if idx < len(lines) and set(lines[idx]) == "=":
        idx += 1
    # Next non-empty lines: author and date
    author, date = "", ""
    if idx < len(lines):
        author = lines[idx]
        idx += 1
    if idx < len(lines):
        date = lines[idx]
        idx += 1
    # Everything from here is body, until "Share this" or "Explore Other Articles"
    content_lines = []
    for l in lines[idx:]:
        if (
            "Share this" in l 
            or "Looking for a daily reminder" in l 
            or "Explore Other Articles" in l
        ):
            break
        if len(l) > 20:
            content_lines.append(l)
    article = "\n".join(content_lines).strip()
    meta = {
        "title": title,
        "date": date,
        "author": author,
    }
    return article, meta

def get_all_article_links_ui():
    BASE_URL = "https://www.intouch.org/read"
    all_article_links = set()
    LAST_PAGE = 56

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for page_num in tqdm(range(1, LAST_PAGE + 1), desc="Paging"):
            url = f"{BASE_URL}?&page={page_num}"
            try:
                page.goto(url, timeout=60000)
                page.wait_for_timeout(1500)
                anchors = page.query_selector_all("a")
                for a in anchors:
                    href = a.get_attribute("href")
                    if (
                        href and (
                            href.startswith("/read/articles/")
                            or href.startswith("/read/daily-devotions/")
                        ) and "#" not in href
                    ):
                        full_url = "https://www.intouch.org" + href.split("?")[0]
                        all_article_links.add(full_url)
                log(f"Collected {len(all_article_links)} article URLs so far (page {page_num}/{LAST_PAGE})")
            except Exception as e:
                log(f"Error on page {page_num}: {e}")
        browser.close()
    return sorted(all_article_links)

def main(sequential=True):
    article_links = get_all_article_links_ui()
    log(f"Found {len(article_links)} article URLs. Starting download...")

    seen_urls = set()
    seen_hashes = set()

    for idx, article_url in enumerate(tqdm(article_links, desc="Articles")):
        if article_url in seen_urls:
            log(f"[{idx+1}/{len(article_links)}] Skipped duplicate URL: {article_url}")
            continue
        seen_urls.add(article_url)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(article_url, timeout=60000)
                article_txt, meta = extract_full_article(page)
                if not article_txt or len(article_txt.split()) < 50:
                    log(f"NO ARTICLE or too short for: {article_url}")
                    continue
                meta["url"] = article_url
                meta["word_count"] = len(article_txt.split())
                meta["hash"] = compute_hash(article_txt)
                if meta['hash'] in seen_hashes:
                    log(f"[{idx+1}/{len(article_links)}] Skipped duplicate content hash: {meta['title']}")
                    continue
                seen_hashes.add(meta['hash'])
                if already_downloaded(meta['hash']):
                    log(f"[{idx+1}/{len(article_links)}] Already downloaded: {meta['title']}")
                    continue
                save_article(article_txt, meta)
                log(f"[{idx+1}/{len(article_links)}] Saved: {meta['title']} ({meta['date']}, {meta['word_count']} words)")
                time.sleep(1)
            except PlaywrightTimeout:
                log(f"[{idx+1}] TIMEOUT for: {article_url}")
            except Exception as e:
                log(f"[{idx+1}] ERROR for: {article_url} -> {e}")
            finally:
                browser.close()
    log("Finished Intouch Ministries article scrape.")

if __name__ == "__main__":
    use_sequential = True
    if "--batch" in sys.argv:
        use_sequential = False
    main(sequential=use_sequential)
