"""
Q&A Unlock & Download (Playwright-based)
==========================================
For paywalled Q&A that require browser interaction to unlock.
Opens pages in parallel batches for speed.

Requires: playwright (pip install playwright && playwright install chromium)

Usage:
    python qa/qa_unlock.py
    python qa/qa_unlock.py --batch-size 3
"""

import asyncio
import json
import os
import sys
import re
from datetime import datetime
from playwright.async_api import async_playwright

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

    return config


def sanitize_filename(name, max_len=80):
    """Sanitize filename by removing illegal characters."""
    name = re.sub(r'[\\/*?:"<>|\n\r\t]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:max_len] if len(name) > max_len else name


def is_already_good(qa_dir):
    """Check if a Q&A already has substantial answer content."""
    txt = os.path.join(qa_dir, "qa.txt")
    if not os.path.exists(txt):
        return False
    with open(txt, "r", encoding="utf-8") as f:
        content = f.read()
    parts = content.split("=" * 60)
    answer = parts[-1].strip() if len(parts) > 1 else ""
    return len(answer) > 150


async def process_one(context, config, idx, qa, qa_dir):
    """Process a single Q&A: navigate, unlock, extract."""
    os.makedirs(qa_dir, exist_ok=True)
    title = qa["question"][:50]
    page = await context.new_page()

    try:
        base_url = config["base_url"]
        qa_page_tpl = config.get("api_paths", {}).get("qa_page", "/p/{qa_id}")
        url = base_url + qa_page_tpl.format(qa_id=qa["id"])
        print(f"  [{idx}] {title}")

        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # Click unlock button if present
        btn = page.locator('[node-type="free_look_btn"]')
        if await btn.count() > 0:
            await btn.click()
            await asyncio.sleep(4)

        # Extract answer
        answer_text = await page.evaluate("""
            () => {
                const sels = ['.answer_con', '.answer_text',
                    '[node-type="answer_text"]', '[node-type="answer_content"]',
                    '.main_answer .WB_text', '.main_answer'];
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el && el.innerText.trim().length > 100) return el.innerText.trim();
                }
                const wrap = document.querySelector('.WB_answer_wrap');
                return wrap ? wrap.innerText.trim() : '';
            }
        """)

        question_text = await page.evaluate("""
            () => {
                const el = document.querySelector('.ask_con, [node-type="askTitle"]');
                return el ? el.innerText.trim() : '';
            }
        """)

        print(f"  [{idx}] answer: {len(answer_text)} chars")

        # Save TXT
        with open(os.path.join(qa_dir, "qa.txt"), "w", encoding="utf-8") as f:
            f.write(f"Question: {question_text or qa['question']}\n")
            if qa.get("questioner"):
                f.write(f"Questioner: {qa['questioner']}\n")
            if qa.get("price_info"):
                f.write(f"Price: {qa['price_info']}\n")
            if qa.get("date"):
                f.write(f"Date: {qa['date']}\n")
            f.write("=" * 60 + "\n\n")
            f.write(answer_text or "(empty)")

        # Save HTML
        q = question_text or qa["question"]
        html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>Q&A: {q[:100]}</title>
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
        <h2>{q}</h2>
        <div class="meta">
            {qa.get('questioner', '')} | {qa.get('price_info', '')} | {qa.get('date', '')}
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

        return True

    except Exception as e:
        print(f"  [{idx}] FAILED: {e}")
        return False
    finally:
        await page.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Q&A Unlock & Download (Playwright)")
    parser.add_argument("--config", default=CONFIG_FILE, help="Path to config file")
    parser.add_argument("--batch-size", type=int, default=5, help="Parallel batch size")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    global CONFIG_FILE
    if args.config != CONFIG_FILE:
        CONFIG_FILE = args.config

    config = load_config()

    save_dir = config.get("qa_save_dir", "./qa/output")
    qa_list_file = os.path.join(save_dir, "_qa_list.json")

    if not os.path.exists(qa_list_file):
        print(f"[Error] {qa_list_file} not found.")
        print("  Run qa_downloader.py first to generate the Q&A list.")
        sys.exit(1)

    with open(qa_list_file, "r", encoding="utf-8") as f:
        qa_list = json.load(f)

    print("=" * 60)
    print("  Q&A Unlock & Download (Playwright)")
    print("=" * 60)

    # Find items that need browser unlock
    needs = []
    for idx, qa in enumerate(qa_list, 1):
        safe_title = sanitize_filename(qa["question"][:60] or f"qa_{idx}")
        qa_dir = os.path.join(save_dir, f"{idx:03d}_{safe_title}")
        if not is_already_good(qa_dir):
            needs.append((idx, qa, qa_dir))

    print(f"  Total: {len(qa_list)}, Need unlock: {len(needs)}")
    if not needs:
        print("  All Q&A already have full answers!")
        return

    base_url = config["base_url"]
    domain = base_url.replace("https://", "").replace("http://", "").split("/")[0]

    async with async_playwright() as p:
        launch_args = {"headless": args.headless}
        browser = await p.chromium.launch(**launch_args)

        ctx_args = {}
        proxy = config.get("proxy")
        if proxy:
            ctx_args["proxy"] = {"server": proxy}

        context = await browser.new_context(**ctx_args)

        # Inject cookies
        for name, value in config["_cookies"].items():
            await context.add_cookies([{
                "name": name, "value": value,
                "domain": f".{domain}", "path": "/",
            }])

        print(f"  Browser launched, cookies injected\n")

        success = fail = 0
        total = len(needs)
        batch_size = args.batch_size

        for batch_start in range(0, total, batch_size):
            batch = needs[batch_start:batch_start + batch_size]
            print(f"  --- Batch {batch_start // batch_size + 1} ({len(batch)} items) ---")

            tasks = [process_one(context, config, idx, qa, qa_dir) for idx, qa, qa_dir in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    fail += 1
                elif r:
                    success += 1
                else:
                    fail += 1

            await asyncio.sleep(2)

        await browser.close()

    print(f"\n{'='*60}")
    print(f"  Done! Success: {success}, Failed: {fail}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
