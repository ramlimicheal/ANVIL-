"""
ANVIL Vision Capture — Renders HTML to screenshot via headless browser.
Uses Playwright if available, falls back to system browser CDP.
"""

import os
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple


def capture_html_to_png(
    html_path: str,
    output_path: str,
    viewport: Tuple[int, int] = (1440, 900),
    full_page: bool = True,
    wait_ms: int = 2000,
) -> str:
    """Render an HTML file to a PNG screenshot.

    Tries in order:
    1. Playwright (most reliable)
    2. Chrome/Brave headless CLI (no deps needed)

    Returns: path to the generated PNG.
    """
    html_path = os.path.abspath(html_path)
    output_path = os.path.abspath(output_path)

    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    # Attempt 1: Playwright
    try:
        return _capture_playwright(html_path, output_path, viewport, full_page, wait_ms)
    except ImportError:
        pass

    # Attempt 2: Headless Chrome/Brave CLI
    return _capture_headless_chrome(html_path, output_path, viewport)


def _capture_playwright(
    html_path: str,
    output_path: str,
    viewport: Tuple[int, int],
    full_page: bool,
    wait_ms: int,
) -> str:
    """Capture using Playwright."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        page.goto(f"file://{html_path}")
        page.wait_for_timeout(wait_ms)  # Wait for charts/animations to render
        page.screenshot(path=output_path, full_page=full_page)
        browser.close()

    return output_path


def _capture_headless_chrome(
    html_path: str,
    output_path: str,
    viewport: Tuple[int, int],
) -> str:
    """Capture using headless Chrome/Brave CLI."""
    # Find browser binary
    browser_paths = [
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]

    browser_bin = None
    for path in browser_paths:
        if os.path.exists(path):
            browser_bin = path
            break

    if not browser_bin:
        raise RuntimeError(
            "No supported browser found for headless capture. "
            "Install playwright: pip install playwright && playwright install chromium"
        )

    cmd = [
        browser_bin,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--window-size={viewport[0]},{viewport[1]}",
        f"--screenshot={output_path}",
        f"file://{html_path}",
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=15)
    if not os.path.exists(output_path):
        raise RuntimeError(f"Screenshot capture failed: {result.stderr.decode()[:200]}")

    return output_path
