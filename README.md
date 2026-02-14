# Article Downloader

Batch download articles from a user's profile page. Supports premium/paid content (with valid access), breakpoint resume, and saves in both HTML and plain text.

## Features

- Batch download all articles from a target user
- Saves articles as **formatted HTML** and **plain text**
- Downloads inline images and cover images
- Breakpoint resume — re-run to skip already downloaded articles
- Configurable delays to avoid rate limiting
- Proxy support

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Copy the example config:

```bash
cp config.example.json config.json
```

3. Edit `config.json`:
   - Set `base_url` to the target site URL
   - Set `target_uid` to the user ID you want to download from
   - Fill in `cookies` — open browser DevTools (F12 → Network tab), pick any request, and copy the cookie values
   - Map cookie names in `cookie_names` to match the site's actual cookie names
   - Optionally set `proxy` (e.g. `"http://127.0.0.1:7890"`)

## Usage

**List articles without downloading:**

```bash
python downloader.py --list-only
```

**Download all articles:**

```bash
python downloader.py
```

**Start from a specific article:**

```bash
python downloader.py --start 20
```

**Skip image downloads:**

```bash
python downloader.py --no-images
```

**Use a custom config file:**

```bash
python downloader.py --config my_config.json
```

## Output Structure

```
output/
├── _article_list.json          # Full article index
├── _progress.json              # Download progress (for resume)
├── 001_Article Title/
│   ├── article.html            # Formatted HTML
│   ├── article.txt             # Plain text
│   ├── metadata.json           # Article metadata
│   ├── cover.jpg               # Cover image
│   └── images/                 # Inline images
│       ├── img_000.jpg
│       └── img_001.jpg
├── 002_Another Article/
│   └── ...
```

## Notes

- Cookies expire periodically — if you get HTTP 403 or login errors, refresh your cookies from the browser
- The tool respects rate limits with configurable delays between requests
- Already downloaded articles are skipped automatically on re-run

## License

MIT
