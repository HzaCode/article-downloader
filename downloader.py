"""
Article Batch Downloader
========================
Batch download articles from a user's profile page using cookies authentication.
Supports paid/premium content (requires valid access), breakpoint resume,
and saves articles in both HTML and plain text formats.

Usage:
    1. Copy config.example.json to config.json
    2. Fill in your base_url, cookies, and target user ID
    3. Run: python downloader.py

See README.md for detailed instructions.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import os
import sys
import time
import argparse
from datetime import datetime
from urllib.parse import urlparse


CONFIG_FILE = "config.json"


def load_config():
    """Load configuration from config.json."""
    if not os.path.exists(CONFIG_FILE):
        print(f"[Error] {CONFIG_FILE} not found.")
        print("  Please copy config.example.json to config.json and fill in your settings.")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    config["_cookies"] = {k: v for k, v in config.get("cookies", {}).items() if v}

    if not config.get("base_url") or "example.com" in config["base_url"]:
        print("[Error] 'base_url' must be set to the real target site URL.")
        sys.exit(1)

    if not config.get("target_uid"):
        print("[Error] 'target_uid' is required.")
        sys.exit(1)

    # Validate API paths
    for key in ("api_profile", "api_articles", "article_page"):
        if not config.get("api_paths", {}).get(key):
            print(f"[Error] 'api_paths.{key}' is required.")
            sys.exit(1)

    return config


def sanitize_filename(name, max_len=80):
    """Sanitize filename by removing illegal characters."""
    name = re.sub(r'[\\/*?:"<>|\n\r\t]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:max_len] if len(name) > max_len else name


def load_progress(save_dir):
    """Load download progress."""
    path = os.path.join(save_dir, "_progress.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"downloaded": []}


def save_progress(save_dir, progress):
    """Save download progress."""
    path = os.path.join(save_dir, "_progress.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def create_session(config):
    """Create a requests session with cookies and headers."""
    session = requests.Session()
    session.cookies.update(config["_cookies"])

    base_url = config["base_url"]
    xsrf = config["_cookies"].get("XSRF-TOKEN", "")

    session.headers.update({
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ),
        "x-xsrf-token": xsrf,
        "referer": f"{base_url}/u/{config['target_uid']}",
        "accept": "application/json, text/plain, */*",
    })

    proxy = config.get("proxy")
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})

    return session


def fetch_article_list(session, config, max_pages=200):
    """Fetch all articles from a user's profile via API."""
    base_url = config["base_url"]
    uid = config["target_uid"]
    page_delay = config.get("delay_between_pages", 1)
    api_tpl = config["api_paths"]["api_articles"]

    all_articles = []
    page = 1

    while page <= max_pages:
        url = base_url + api_tpl.format(uid=uid, page=page)
        print(f"  Fetching page {page}...", end=" ")

        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                print(f"HTTP {r.status_code}")
                break

            data = r.json().get("data", {})
            items = data.get("list", [])

            if not items:
                print("no more data")
                break

            count = 0
            for item in items:
                page_info = item.get("page_info", {})
                if page_info.get("type") == "24" or page_info.get("object_type") == "article":
                    article_id = page_info.get("page_id", "")
                    title = page_info.get("content1", "") or item.get("text_raw", "")[:50]
                    author = item.get("user", {}).get("screen_name", "")

                    page_tpl = config["api_paths"]["article_page"]
                    article_url = base_url + page_tpl.format(article_id=article_id)

                    all_articles.append({
                        "article_id": article_id,
                        "title": title,
                        "author": author,
                        "post_id": item.get("id", ""),
                        "created_at": item.get("created_at", ""),
                        "summary": item.get("text_raw", ""),
                        "cover_pic": page_info.get("page_pic", ""),
                        "page_url": article_url,
                    })
                    count += 1

            print(f"found {count} articles (of {len(items)} posts)")

            if len(items) < 20:
                print("  Reached last page")
                break

            page += 1
            time.sleep(page_delay)

        except Exception as e:
            print(f"error: {e}")
            break

    return all_articles


def extract_article_content(html_text):
    """Extract article content from the HTML page."""
    result = {
        "title": "",
        "content_html": "",
        "content_text": "",
        "images": [],
    }

    soup = BeautifulSoup(html_text, "html.parser")

    # Title
    title_el = soup.find("div", class_="title") or soup.find("h1")
    if title_el:
        result["title"] = title_el.get_text(strip=True)

    # Content is rendered client-side inside filterXSS("...")
    xss_match = re.search(r'filterXSS\("(.*?)"\s*(?:,|\))', html_text, re.DOTALL)
    if xss_match:
        raw = xss_match.group(1)
        try:
            html = raw.encode("utf-8").decode("unicode_escape")
        except Exception:
            html = raw
        html = html.replace("\\" + "/", "/")
        html = html.replace('\\"', '"')
        html = html.replace("\\'", "'")
        result["content_html"] = html

        inner = BeautifulSoup(html, "html.parser")
        result["content_text"] = inner.get_text("\n", strip=True)

        for img in inner.find_all("img"):
            src = img.get("src", img.get("data-src", ""))
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                if not src.startswith("data:") and "emotion" not in src:
                    result["images"].append(src)

    # Fallback
    if not result["content_html"]:
        div = soup.find("div", id="article_content") or soup.find("div", class_="article_content")
        if div and div.get_text(strip=True):
            result["content_html"] = str(div)
            result["content_text"] = div.get_text("\n", strip=True)

    return result


def download_images(session, images, img_dir):
    """Download images to local directory."""
    if not images:
        return 0
    os.makedirs(img_dir, exist_ok=True)
    count = 0
    for idx, url in enumerate(images):
        try:
            ext = os.path.splitext(urlparse(url).path)[1]
            if not ext or len(ext) > 5:
                ext = ".jpg"
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                with open(os.path.join(img_dir, f"img_{idx:03d}{ext}"), "wb") as f:
                    f.write(r.content)
                count += 1
        except Exception as e:
            print(f"    [image] failed #{idx}: {e}")
    return count


def save_article(article_info, content, save_dir, index):
    """Save a single article to disk (HTML + TXT + metadata)."""
    title = content.get("title") or article_info.get("title", f"article_{index}")
    author = article_info.get("author", "")
    created_at = article_info.get("created_at", "")
    safe_title = sanitize_filename(title)
    article_dir = os.path.join(save_dir, f"{index:03d}_{safe_title}")
    os.makedirs(article_dir, exist_ok=True)

    # HTML
    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{
            max-width: 800px; margin: 40px auto; padding: 0 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                         "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
            line-height: 1.8; color: #333; background: #fff;
        }}
        h1 {{ font-size: 24px; margin-bottom: 10px; }}
        .meta {{ color: #999; font-size: 13px; margin-bottom: 30px;
                 padding-bottom: 15px; border-bottom: 1px solid #eee; }}
        .article-body img {{ max-width: 100%; height: auto; margin: 10px 0; border-radius: 4px; }}
        .article-body p {{ margin: 12px 0; }}
        .footer {{ margin-top: 40px; padding-top: 15px; border-top: 1px solid #eee;
                   color: #aaa; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="meta">
        {f'<span>Author: {author}</span>' if author else ''}
        {f' | <span>Date: {created_at}</span>' if created_at else ''}
    </div>
    <div class="article-body">
        {content.get('content_html', '<p>(empty)</p>')}
    </div>
    <div class="footer">
        <p>Downloaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</body>
</html>"""

    with open(os.path.join(article_dir, "article.html"), "w", encoding="utf-8") as f:
        f.write(html_out)

    # TXT
    with open(os.path.join(article_dir, "article.txt"), "w", encoding="utf-8") as f:
        f.write(f"Title: {title}\n")
        if author:
            f.write(f"Author: {author}\n")
        if created_at:
            f.write(f"Date: {created_at}\n")
        f.write("=" * 60 + "\n\n")
        f.write(content.get("content_text", "(empty)"))

    # Metadata
    with open(os.path.join(article_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump({
            "title": title,
            "author": author,
            "created_at": created_at,
            "article_id": article_info.get("article_id", ""),
            "content_length": len(content.get("content_text", "")),
            "image_count": len(content.get("images", [])),
        }, f, ensure_ascii=False, indent=2)

    return article_dir


def main():
    parser = argparse.ArgumentParser(description="Article Batch Downloader")
    parser.add_argument("--config", default=CONFIG_FILE, help="Path to config file")
    parser.add_argument("--list-only", action="store_true", help="List articles without downloading")
    parser.add_argument("--start", type=int, default=1, help="Start from Nth article")
    parser.add_argument("--no-images", action="store_true", help="Skip image downloads")
    args = parser.parse_args()

    global CONFIG_FILE
    CONFIG_FILE = args.config

    config = load_config()

    uid = config["target_uid"]
    save_dir = config.get("save_dir", "./output")
    delay = config.get("delay_between_articles", 2)

    os.makedirs(save_dir, exist_ok=True)

    print("=" * 60)
    print("  Article Batch Downloader")
    print("=" * 60)
    print(f"  Target   : {uid}")
    print(f"  Output   : {save_dir}")
    print(f"  Proxy    : {config.get('proxy') or 'none'}")
    print("=" * 60)

    session = create_session(config)

    # 1. Verify
    print("\n[1/4] Verifying login status...")
    try:
        url = config["base_url"] + config["api_paths"]["api_profile"].format(uid=uid)
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            user = r.json().get("data", {}).get("user", {})
            print(f"  OK - target user: {user.get('screen_name', 'unknown')}")
        else:
            print(f"  FAILED (HTTP {r.status_code}) - cookies may have expired")
            return
    except Exception as e:
        print(f"  FAILED: {e}")
        return

    # 2. List
    print(f"\n[2/4] Fetching article list...")
    articles = fetch_article_list(session, config)

    if not articles:
        print("  No articles found!")
        return

    seen = set()
    articles = [a for a in articles if not (a["article_id"] in seen or seen.add(a["article_id"]))]

    print(f"\n  Found {len(articles)} articles")

    with open(os.path.join(save_dir, "_article_list.json"), "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    for i, a in enumerate(articles, 1):
        d = a["created_at"][:16] if a["created_at"] else "unknown"
        print(f"    {i:3d}. [{d}] {a['title'][:55]}")

    if args.list_only:
        print("\n  (list-only mode)")
        return

    # 3. Download
    progress = load_progress(save_dir)
    done_ids = set(progress.get("downloaded", []))

    print(f"\n[3/4] Downloading articles...")
    success = fail = skip = 0
    total = len(articles)

    for idx, article in enumerate(articles, 1):
        if idx < args.start:
            skip += 1
            continue
        if article["article_id"] in done_ids:
            print(f"  [{idx}/{total}] skipped: {article['title'][:40]}")
            skip += 1
            continue

        print(f"\n  [{idx}/{total}] {article['title'][:55]}")

        try:
            r = session.get(article["page_url"], timeout=20)
            if r.status_code != 200:
                print(f"    FAILED: HTTP {r.status_code}")
                fail += 1
                continue

            content = extract_article_content(r.text)
            print(f"    content: {len(content.get('content_text', ''))} chars, "
                  f"{len(content.get('images', []))} images")

            article_dir = save_article(article, content, save_dir, idx)

            if not args.no_images and content.get("images"):
                n = download_images(session, content["images"], os.path.join(article_dir, "images"))
                print(f"    images: {n}/{len(content['images'])}")

            if article.get("cover_pic"):
                try:
                    cr = session.get(article["cover_pic"], timeout=10)
                    if cr.status_code == 200:
                        with open(os.path.join(article_dir, "cover.jpg"), "wb") as f:
                            f.write(cr.content)
                except Exception:
                    pass

            print(f"    saved: {article_dir}")
            success += 1
            progress["downloaded"].append(article["article_id"])
            save_progress(save_dir, progress)

        except Exception as e:
            print(f"    FAILED: {e}")
            fail += 1

        if idx < total:
            time.sleep(delay)

    # 4. Summary
    print(f"\n{'='*60}")
    print(f"  [4/4] Done!")
    print(f"{'='*60}")
    print(f"  Success : {success}")
    print(f"  Failed  : {fail}")
    print(f"  Skipped : {skip}")
    print(f"  Output  : {save_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
