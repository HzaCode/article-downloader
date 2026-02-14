"""
Q&A Downloader (requests-based)
================================
Download Q&A answers that are already unlocked (server-rendered).
Uses the same config.json as the main article downloader.

For paywalled Q&A that require browser interaction, use qa_unlock.py instead.

Usage:
    python qa/qa_downloader.py
    python qa/qa_downloader.py --list-only
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

# Config is in parent directory
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def load_config():
    """Load configuration from config.json in project root."""
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


def fetch_qa_list(session, config, max_pages=200):
    """Fetch all Q&A items from the article list API."""
    base_url = config["base_url"]
    uid = config["target_uid"]
    api_tpl = config["api_paths"]["api_articles"]
    page_delay = config.get("delay_between_pages", 1)

    all_qa = []
    seen = set()
    page = 1

    while page <= max_pages:
        url = base_url + api_tpl.format(uid=uid, page=page)
        print(f"  Fetching page {page}...", end=" ")

        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                print(f"HTTP {r.status_code}")
                break

            items = r.json().get("data", {}).get("list", [])
            if not items:
                print("no more data")
                break

            count = 0
            for item in items:
                pi = item.get("page_info", {})
                aid = pi.get("page_id", "")
                if (pi.get("object_type") == "wenda" or pi.get("source_type") == "wenda") and aid not in seen:
                    seen.add(aid)
                    all_qa.append({
                        "id": aid,
                        "question": pi.get("content1", pi.get("page_desc", "")),
                        "questioner": pi.get("content3", ""),
                        "price_info": pi.get("content2", ""),
                        "author": item.get("user", {}).get("screen_name", ""),
                        "date": item.get("created_at", ""),
                        "summary": item.get("text_raw", ""),
                    })
                    count += 1

            print(f"found {count} Q&A (of {len(items)} posts)")

            if len(items) < 20:
                break
            page += 1
            time.sleep(page_delay)

        except Exception as e:
            print(f"error: {e}")
            break

    return all_qa


def extract_qa_content(html):
    """Extract Q&A content from the /p/ page HTML."""
    soup = BeautifulSoup(html, "html.parser")

    result = {"question": "", "answer": ""}

    q_div = soup.find(class_="ask_con") or soup.find(attrs={"node-type": "askTitle"})
    if q_div:
        result["question"] = q_div.get_text("\n", strip=True)

    a_div = soup.find(class_="main_answer")
    if a_div:
        result["answer"] = a_div.get_text("\n", strip=True)

    if not result["answer"]:
        wrap = soup.find(class_="WB_answer_wrap")
        if wrap:
            result["answer"] = wrap.get_text("\n", strip=True)

    return result


def save_qa(qa_info, content, save_dir, index):
    """Save a single Q&A to disk."""
    title = qa_info.get("question", f"qa_{index}")[:60]
    safe_title = sanitize_filename(title)
    qa_dir = os.path.join(save_dir, f"{index:03d}_{safe_title}")
    os.makedirs(qa_dir, exist_ok=True)

    question_text = content.get("question") or qa_info.get("question", "")
    answer_text = content.get("answer", "")

    # HTML
    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>Q&A: {question_text[:100]}</title>
    <style>
        body {{ max-width: 800px; margin: 40px auto; padding: 0 20px;
               font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
               line-height: 1.8; color: #333; }}
        .question {{ background: #f7f7f7; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .question h2 {{ font-size: 18px; margin: 0 0 10px; }}
        .meta {{ color: #999; font-size: 13px; }}
        .answer {{ padding: 20px 0; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee;
                   color: #aaa; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="question">
        <h2>{question_text}</h2>
        <div class="meta">
            {f'Questioner: {qa_info.get("questioner", "")}' if qa_info.get('questioner') else ''}
            {f' | {qa_info.get("price_info", "")}' if qa_info.get('price_info') else ''}
            {f' | {qa_info.get("date", "")}' if qa_info.get('date') else ''}
        </div>
    </div>
    <div class="answer">
        <p>{'</p><p>'.join(answer_text.split(chr(10))) if answer_text else '(empty)'}</p>
    </div>
    <div class="footer">
        <p>Downloaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</body>
</html>"""
    with open(os.path.join(qa_dir, "qa.html"), "w", encoding="utf-8") as f:
        f.write(html_out)

    # TXT
    with open(os.path.join(qa_dir, "qa.txt"), "w", encoding="utf-8") as f:
        f.write(f"Question: {question_text}\n")
        if qa_info.get("questioner"):
            f.write(f"Questioner: {qa_info['questioner']}\n")
        if qa_info.get("price_info"):
            f.write(f"Price: {qa_info['price_info']}\n")
        if qa_info.get("date"):
            f.write(f"Date: {qa_info['date']}\n")
        f.write("=" * 60 + "\n\n")
        f.write(answer_text or "(empty)")

    return qa_dir


def main():
    parser = argparse.ArgumentParser(description="Q&A Downloader (requests-based)")
    parser.add_argument("--config", default=CONFIG_FILE, help="Path to config file")
    parser.add_argument("--list-only", action="store_true", help="List Q&A without downloading")
    parser.add_argument("--start", type=int, default=1, help="Start from Nth item")
    args = parser.parse_args()

    global CONFIG_FILE
    if args.config != CONFIG_FILE:
        CONFIG_FILE = args.config

    config = load_config()

    base_url = config["base_url"]
    qa_page_tpl = config.get("api_paths", {}).get("qa_page", "/p/{qa_id}")
    save_dir = config.get("qa_save_dir", "./qa/output")
    delay = config.get("delay_between_articles", 2)

    os.makedirs(save_dir, exist_ok=True)

    print("=" * 60)
    print("  Q&A Downloader")
    print("=" * 60)

    session = create_session(config)

    # 1. Verify
    print("\n[1/3] Verifying login...")
    try:
        uid = config["target_uid"]
        url = base_url + config["api_paths"]["api_profile"].format(uid=uid)
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            user = r.json().get("data", {}).get("user", {})
            print(f"  OK - target: {user.get('screen_name', 'unknown')}")
        else:
            print(f"  FAILED (HTTP {r.status_code})")
            return
    except Exception as e:
        print(f"  FAILED: {e}")
        return

    # 2. Fetch list
    print("\n[2/3] Fetching Q&A list...")
    qa_list = fetch_qa_list(session, config)
    if not qa_list:
        print("  No Q&A found!")
        return

    print(f"\n  Found {len(qa_list)} Q&A items")

    with open(os.path.join(save_dir, "_qa_list.json"), "w", encoding="utf-8") as f:
        json.dump(qa_list, f, ensure_ascii=False, indent=2)

    for i, q in enumerate(qa_list, 1):
        d = q["date"][:16] if q["date"] else "unknown"
        print(f"    {i:3d}. [{d}] {q['question'][:55]}")

    if args.list_only:
        print("\n  (list-only mode)")
        return

    # 3. Download
    progress = load_progress(save_dir)
    done_ids = set(progress.get("downloaded", []))

    print(f"\n[3/3] Downloading Q&A...")
    success = fail = skip = 0
    total = len(qa_list)

    for idx, qa in enumerate(qa_list, 1):
        if idx < args.start:
            skip += 1
            continue
        if qa["id"] in done_ids:
            skip += 1
            continue

        print(f"\n  [{idx}/{total}] {qa['question'][:55]}")

        try:
            page_url = base_url + qa_page_tpl.format(qa_id=qa["id"])
            r = session.get(page_url, timeout=20)
            if r.status_code != 200:
                print(f"    FAILED: HTTP {r.status_code}")
                fail += 1
                continue

            content = extract_qa_content(r.text)
            answer_len = len(content.get("answer", ""))
            print(f"    answer: {answer_len} chars")

            if answer_len < 150:
                print(f"    NOTE: short answer - may need qa_unlock.py for browser unlock")

            save_qa(qa, content, save_dir, idx)
            success += 1

            progress["downloaded"].append(qa["id"])
            save_progress(save_dir, progress)

        except Exception as e:
            print(f"    FAILED: {e}")
            fail += 1

        if idx < total:
            time.sleep(delay)

    print(f"\n{'='*60}")
    print(f"  Done! Success: {success}, Failed: {fail}, Skipped: {skip}")
    print(f"  Output: {save_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
