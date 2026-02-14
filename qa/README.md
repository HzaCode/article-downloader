# Q&A Downloader

Download paid Q&A (question & answer) content. Two scripts handle different scenarios:

| Script | Method | Use case |
|--------|--------|----------|
| `qa_downloader.py` | requests | Already-unlocked Q&A (server-rendered answers) |
| `qa_unlock.py` | Playwright (browser) | Paywalled Q&A requiring browser unlock |

## Workflow

**Step 1** — Run the requests-based downloader first. It fetches all Q&A and downloads whatever is already accessible:

```bash
python qa/qa_downloader.py
```

**Step 2** — Check which Q&A have short/empty answers (paywalled). Then run the browser-based unlocker to handle those:

```bash
python qa/qa_unlock.py
```

The unlock script opens pages in parallel batches (default 5) for speed.

## Options

### qa_downloader.py

```bash
python qa/qa_downloader.py --list-only       # List Q&A without downloading
python qa/qa_downloader.py --start 10        # Start from 10th item
python qa/qa_downloader.py --config path.json # Custom config file
```

### qa_unlock.py

```bash
python qa/qa_unlock.py --batch-size 3   # Adjust parallel batch size
python qa/qa_unlock.py --headless       # Run browser in headless mode
```

## Setup

Both scripts read from the project root `config.json`. Make sure `api_paths.qa_page` is set.

For `qa_unlock.py`, install Playwright and its browser:

```bash
pip install playwright
playwright install chromium
```

## Output

```
qa/output/
├── _qa_list.json
├── _progress.json
├── 001_Question Title/
│   ├── qa.html
│   └── qa.txt
├── 002_Another Question/
│   └── ...
```
