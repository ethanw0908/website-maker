import asyncio
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright


VIEWPORTS = {
    "mobile": {"width": 390, "height": 844},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1440, "height": 1100},
}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _render(base_url: str, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: dict[str, str] = {}
    console_errors: list[str] = []
    page_errors: list[str] = []
    overflow: dict[str, bool] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            for name, viewport in VIEWPORTS.items():
                context = await browser.new_context(
                    viewport=viewport,
                    ignore_https_errors=True,
                    reduced_motion="reduce",
                )
                page = await context.new_page()
                page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                response = await page.goto(base_url, wait_until="networkidle", timeout=45_000)
                if response and response.status >= 400:
                    page_errors.append(f"{name}: HTTP {response.status} for {base_url}")
                await page.wait_for_timeout(500)
                overflow[name] = bool(
                    await page.evaluate(
                        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"
                    )
                )
                path = output_dir / f"{name}.png"
                await page.screenshot(path=str(path), full_page=True)
                screenshots[name] = str(path)
                await context.close()
        finally:
            await browser.close()

    return {
        "screenshots": screenshots,
        "console_errors": list(dict.fromkeys(console_errors))[:20],
        "page_errors": list(dict.fromkeys(page_errors))[:20],
        "horizontal_overflow": overflow,
        "passed": not page_errors and not any(overflow.values()),
    }


def render_site(root: Path) -> dict:
    """Serve a generated static site locally and capture review screenshots."""
    index = root / "index.html"
    if not index.exists():
        return {
            "screenshots": {},
            "console_errors": [],
            "page_errors": ["index.html is missing"],
            "horizontal_overflow": {},
            "passed": False,
        }

    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 8
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        else:
            raise RuntimeError("Timed out starting the local preview server")

        return asyncio.run(
            _render(
                f"http://127.0.0.1:{port}/",
                root / "_agent" / "screenshots",
            )
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
