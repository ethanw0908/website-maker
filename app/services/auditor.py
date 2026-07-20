import asyncio
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import dns.resolver
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PREFERRED_PREFIXES = ("info@", "service@", "hello@", "contact@", "office@", "sales@")


@dataclass
class ContactCandidate:
    email: str | None
    email_source_url: str | None
    source_type: str | None
    contact_form_url: str | None
    confidence: float
    mx_valid: bool | None


class WebsiteAuditor:
    def __init__(self, screenshot_dir: Path) -> None:
        self.screenshot_dir = screenshot_dir
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def audit(self, url: str) -> dict:
        result = {
            "reachable": False,
            "https_enabled": url.lower().startswith("https://"),
            "mobile_responsive": False,
            "has_call_to_action": False,
            "has_service_information": False,
            "outdated_visual_signals": False,
            "broken_links": [],
            "metadata": {},
            "screenshot_paths": [],
            "contact": asdict(ContactCandidate(None, None, None, None, 0, None)),
        }
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                result["reachable"] = bool(response and response.ok)
                await page.wait_for_timeout(900)
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")
                text = soup.get_text(" ", strip=True).lower()

                viewport = await page.locator('meta[name="viewport"]').count()
                result["mobile_responsive"] = viewport > 0
                result["has_call_to_action"] = any(term in text for term in (
                    "call now", "contact us", "book now", "request a quote", "schedule", "reserve"
                ))
                result["has_service_information"] = any(term in text for term in (
                    "services", "menu", "treatments", "what we do", "our work"
                ))
                result["outdated_visual_signals"] = any(term in html.lower() for term in (
                    "<marquee", "font-family: comic sans", "table width=", "flash"
                ))
                title = await page.title()
                description = await page.locator('meta[name="description"]').get_attribute("content") if await page.locator('meta[name="description"]').count() else None
                result["metadata"] = {"title": title, "description": description}

                desktop = self.screenshot_dir / "desktop.png"
                await page.set_viewport_size({"width": 1440, "height": 1000})
                await page.screenshot(path=str(desktop), full_page=True)
                mobile = self.screenshot_dir / "mobile.png"
                await page.set_viewport_size({"width": 390, "height": 844})
                await page.screenshot(path=str(mobile), full_page=True)
                result["screenshot_paths"] = [str(desktop), str(mobile)]

                result["contact"] = asdict(await self._find_contact(page, soup, url))
                result["broken_links"] = await self._check_internal_links(page, url)
            finally:
                await context.close()
                await browser.close()
        return result

    async def _find_contact(self, page, soup: BeautifulSoup, base_url: str) -> ContactCandidate:
        emails: list[tuple[str, str]] = []
        for link in soup.select('a[href^="mailto:"]'):
            email = link.get("href", "").removeprefix("mailto:").split("?")[0].strip()
            if email:
                emails.append((email, "mailto"))
        for email in EMAIL_PATTERN.findall(soup.get_text(" ")):
            emails.append((email, "visible_text"))

        contact_form_url = None
        for link in soup.select("a[href]"):
            label = link.get_text(" ", strip=True).lower()
            href = link.get("href", "")
            if "contact" in label or "contact" in href.lower():
                contact_form_url = urljoin(base_url, href)
                break

        if not emails:
            return ContactCandidate(None, None, None, contact_form_url, 0, None)
        unique = {email.lower(): source for email, source in emails}
        ranked = sorted(unique.items(), key=lambda item: (not item[0].startswith(PREFERRED_PREFIXES), item[0]))
        email, source_type = ranked[0]
        confidence = 0.95 if source_type == "mailto" else 0.75
        return ContactCandidate(email, page.url, source_type, contact_form_url, confidence, self._validate_mx(email))

    @staticmethod
    def _validate_mx(email: str) -> bool | None:
        try:
            dns.resolver.resolve(email.rsplit("@", 1)[1], "MX", lifetime=3)
            return True
        except Exception:
            return None

    @staticmethod
    async def _check_internal_links(page, base_url: str) -> list[str]:
        host = urlparse(base_url).netloc
        hrefs = await page.locator("a[href]").evaluate_all("els => els.map(e => e.href)")
        links = [href for href in dict.fromkeys(hrefs) if urlparse(href).netloc == host][:20]
        broken: list[str] = []
        request = page.context.request
        for href in links:
            try:
                response = await request.get(href, timeout=8_000)
                if response.status >= 400:
                    broken.append(href)
            except Exception:
                broken.append(href)
            await asyncio.sleep(0.05)
        return broken
