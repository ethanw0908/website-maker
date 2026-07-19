import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

REQUIRED_HTML = ("index.html", "about.html", "services.html", "contact.html")
REQUIRED_SUPPORT = ("robots.txt", "sitemap.xml", "README.md", "vercel.json")
PROHIBITED_PATTERNS = {
    "placeholder text": re.compile(r"\blorem ipsum\b", re.IGNORECASE),
    "unverified superlative": re.compile(r"\bbest in (?:the )?(?:city|area|region)\b", re.IGNORECASE),
    "unverified award claim": re.compile(r"\baward[- ]winning\b", re.IGNORECASE),
    "unverified guarantee": re.compile(r"\bguaranteed results?\b", re.IGNORECASE),
    "unverified rating claim": re.compile(r"\bfive[- ]star service\b", re.IGNORECASE),
}


def _company(brief: dict | None) -> dict:
    return (brief or {}).get("company") or {}


def _ensure_robots_meta(path: Path) -> None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    if soup.html is None:
        html = soup.new_tag("html")
        html.extend(list(soup.contents))
        soup.append(html)
    if soup.head is None:
        head = soup.new_tag("head")
        soup.html.insert(0, head)
    else:
        head = soup.head

    robots = head.find("meta", attrs={"name": re.compile(r"^robots$", re.IGNORECASE)})
    if robots is None:
        robots = soup.new_tag("meta")
        robots["name"] = "robots"
        robots["content"] = "noindex, nofollow"
        head.append(robots)
    else:
        tokens = {
            token.strip().lower()
            for token in str(robots.get("content") or "").split(",")
            if token.strip()
        }
        tokens.update({"noindex", "nofollow"})
        robots["content"] = ", ".join(sorted(tokens))

    path.write_text(str(soup), encoding="utf-8")


def prepare_generated_site(root: Path, brief: dict | None = None) -> list[str]:
    """Repair deterministic preview boilerplate before QA without inventing business facts."""
    root.mkdir(parents=True, exist_ok=True)
    repairs: list[str] = []

    for path in sorted(root.glob("*.html")):
        before = path.read_text(encoding="utf-8", errors="ignore")
        _ensure_robots_meta(path)
        if path.read_text(encoding="utf-8", errors="ignore") != before:
            repairs.append(f"Normalised robots metadata in {path.name}")

    support_files = {
        "robots.txt": "User-agent: *\nDisallow: /\n",
        "vercel.json": json.dumps({"cleanUrls": True, "trailingSlash": False}, indent=2) + "\n",
        "README.md": (
            "# Unofficial concept preview\n\n"
            "This repository is an unsolicited, private website concept. It is not operated by the business, "
            "does not accept bookings, payments, or customer information, and must remain unindexed until approved.\n"
        ),
        "sitemap.xml": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>\n'
        ),
    }
    for name, content in support_files.items():
        path = root / name
        if not path.exists() or not path.read_text(encoding="utf-8", errors="ignore").strip():
            path.write_text(content, encoding="utf-8")
            repairs.append(f"Created {name}")

    return repairs


def validate_generated_site(root: Path, brief: dict | None = None) -> dict:
    failures: list[str] = []
    warnings: list[str] = []

    html_paths = sorted(root.glob("*.html"))
    if not html_paths:
        return {
            "passed": False,
            "failures": ["No top-level HTML files were generated"],
            "warnings": [],
            "html_files": [],
        }

    for required in REQUIRED_HTML:
        path = root / required
        if not path.exists() or not path.read_text(encoding="utf-8", errors="ignore").strip():
            failures.append(f"Missing required page: {required}")

    combined_text: list[str] = []
    combined_html: list[str] = []
    for path in html_paths:
        html = path.read_text(encoding="utf-8", errors="ignore")
        combined_html.append(html.lower())
        soup = BeautifulSoup(html, "lxml")
        combined_text.append(soup.get_text(" ", strip=True).lower())

        robots = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.IGNORECASE)})
        tokens = {
            token.strip().lower()
            for token in str(robots.get("content") if robots else "").split(",")
            if token.strip()
        }
        if not {"noindex", "nofollow"}.issubset(tokens):
            failures.append(f"{path.name} is missing noindex and nofollow robots metadata")

        for form in soup.find_all("form"):
            action = str(form.get("action") or "").strip()
            if action and action not in {"#", "/#"} and not action.lower().startswith("javascript:"):
                warnings.append(f"{path.name} contains a form action; confirm it cannot collect customer data")

    visible_text = "\n".join(combined_text)
    lowered_html = "\n".join(combined_html)
    for label, pattern in PROHIBITED_PATTERNS.items():
        if pattern.search(visible_text):
            failures.append(f"Detected {label}")

    company = _company(brief)
    verified_email = str(company.get("public_email") or "").strip().lower()
    verified_phone = str(company.get("phone") or "").strip()
    if verified_email and "mailto:" not in lowered_html:
        failures.append("Verified email exists, but the site has no mailto contact action")
    if verified_phone and "tel:" not in lowered_html:
        failures.append("Verified phone exists, but the site has no telephone contact action")
    if not verified_email and not verified_phone:
        warnings.append("No verified phone or email was available; contact-link QA was skipped")

    for required in REQUIRED_SUPPORT:
        if not (root / required).exists():
            failures.append(f"Missing required file: {required}")

    return {
        "passed": not failures,
        "failures": failures,
        "warnings": warnings,
        "html_files": [path.name for path in html_paths],
    }
