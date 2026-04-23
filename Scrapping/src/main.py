import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import yaml
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_navigation(page, steps: List[Dict[str, Any]], timeout_ms: int) -> None:
    for idx, step in enumerate(steps, start=1):
        action = step.get("action")
        if not action:
            raise ValueError(f"navigation step #{idx} has no action")

        if action == "goto":
            url = step.get("url")
            if not url:
                raise ValueError(f"goto step #{idx} needs url")
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        elif action == "click":
            selector = step.get("selector")
            if not selector:
                raise ValueError(f"click step #{idx} needs selector")
            page.locator(selector).first.click(timeout=timeout_ms)

        elif action == "fill":
            selector = step.get("selector")
            value = step.get("value")
            if not selector:
                raise ValueError(f"fill step #{idx} needs selector")
            if value is None:
                raise ValueError(f"fill step #{idx} needs value")
            page.locator(selector).first.fill(str(value), timeout=timeout_ms)

        elif action == "wait_for":
            selector = step.get("selector")
            state = step.get("state", "visible")
            if not selector:
                raise ValueError(f"wait_for step #{idx} needs selector")
            page.locator(selector).first.wait_for(state=state, timeout=timeout_ms)

        elif action == "sleep":
            ms = int(step.get("ms", 500))
            page.wait_for_timeout(ms)

        else:
            raise ValueError(f"unsupported action '{action}' at step #{idx}")


def extract_single(page, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for field in fields:
        name = field["name"]
        selector = field["selector"]
        attr = field.get("attr", "text")
        locator = page.locator(selector).first

        if attr == "text":
            row[name] = locator.inner_text().strip()
        else:
            row[name] = locator.get_attribute(attr)

    return row


def extract_list(page, item_selector: str, fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = page.locator(item_selector)
    count = items.count()
    rows: List[Dict[str, Any]] = []

    for i in range(count):
        item = items.nth(i)
        row: Dict[str, Any] = {}

        for field in fields:
            name = field["name"]
            selector = field["selector"]
            attr = field.get("attr", "text")
            locator = item.locator(selector).first

            if attr == "text":
                value = locator.inner_text().strip()
            else:
                value = locator.get_attribute(attr)

            row[name] = value

        rows.append(row)

    return rows


def ensure_output_parent(output_base: str) -> None:
    parent = Path(output_base).parent
    parent.mkdir(parents=True, exist_ok=True)


def write_json(output_base: str, rows: List[Dict[str, Any]]) -> str:
    ensure_output_parent(output_base)
    path = f"{output_base}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return path


def write_csv(output_base: str, rows: List[Dict[str, Any]]) -> str:
    ensure_output_parent(output_base)
    path = f"{output_base}.csv"
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return path

    headers = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return path


def run(config_path: str) -> str:
    config = load_config(config_path)

    start_url = config["start_url"]
    headless = bool(config.get("headless", True))
    timeout_ms = int(config.get("timeout_ms", 20000))

    navigation = config.get("navigation", [])
    extraction = config.get("extraction", {})
    output = config.get("output", {})

    output_format = output.get("format", "json").lower()
    output_path = output.get("path", "output/results")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()

        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=timeout_ms)
            run_navigation(page, navigation, timeout_ms)

            mode = extraction.get("mode", "single")
            fields = extraction.get("fields", [])

            if mode == "single":
                rows = [extract_single(page, fields)]
            elif mode == "list":
                item_selector = extraction.get("item_selector")
                if not item_selector:
                    raise ValueError("extraction.item_selector is required for mode=list")
                rows = extract_list(page, item_selector, fields)
            else:
                raise ValueError(f"unsupported extraction mode: {mode}")

            if output_format == "json":
                return write_json(output_path, rows)
            if output_format == "csv":
                return write_csv(output_path, rows)

            raise ValueError("output.format must be 'json' or 'csv'")

        except PlaywrightTimeoutError as e:
            screenshot_dir = Path("output")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshot_dir / "timeout_error.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            raise RuntimeError(
                f"timeout during scraping. screenshot saved at {screenshot_path}"
            ) from e
        finally:
            browser.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape pages requiring many clicks using config driven steps"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to yaml config (default: config.yaml)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_file = run(args.config)
    print(f"Scraping finished. Output: {output_file}")


if __name__ == "__main__":
    main()
