# Config driven web scraper (many clicks)

This app automates a browser with Playwright, executes many click/fill/wait steps, then extracts data and writes JSON or CSV.

## 1) Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 2) Configure

Copy the example config and edit selectors/actions for your target website:

```bash
cp config.example.yaml config.yaml
```

Main config keys:
- `start_url`: first page to open.
- `navigation`: ordered actions to reach target data.
- `extraction`: what to read from the final page.
- `output`: output format (`json` or `csv`) and output path without extension.

### Supported navigation actions
- `goto`: open a URL.
- `click`: click selector.
- `fill`: fill input selector with value.
- `wait_for`: wait for selector state (`visible`, `attached`, etc).
- `sleep`: wait a fixed amount of milliseconds.

## 3) Run

```bash
python src/main.py --config config.yaml
```

Output example:
- `output/results.json`
- `output/results.csv`

## 4) Notes for dynamic websites

- Prefer stable selectors (`data-testid`, fixed IDs) over visual CSS classes.
- Insert `wait_for` steps before critical clicks.
- If timeout happens, a screenshot is saved to `output/timeout_error.png`.
- For login/session pages, include `fill` and `click` actions in sequence.
