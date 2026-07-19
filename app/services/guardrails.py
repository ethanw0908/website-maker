from pathlib import Path

PROHIBITED_MARKERS = {
    "lorem ipsum",
    "official website",
    "best in the city",
    "award-winning",
    "guaranteed results",
    "five-star service",
}

REQUIRED_NOINDEX = '<meta name="robots" content="noindex, nofollow">'


def validate_generated_site(root: Path, verified_facts: list[str] | None = None) -> dict:
    failures: list[str] = []
    html_files = list(root.glob("*.html"))
    if not html_files:
        failures.append("No top-level HTML files were generated")
        return {"passed": False, "failures": failures}

    combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in html_files)
    lowered = combined.lower()
    if REQUIRED_NOINDEX not in combined:
        failures.append("Preview is missing noindex, nofollow metadata")
    for marker in sorted(PROHIBITED_MARKERS):
        if marker in lowered:
            failures.append(f"Prohibited or unverified phrase detected: {marker}")
    if "mailto:" not in lowered and "tel:" not in lowered:
        failures.append("No verified contact action is present")
    for required in ("index.html", "robots.txt", "sitemap.xml", "README.md", "vercel.json"):
        if not (root / required).exists():
            failures.append(f"Missing required file: {required}")

    return {"passed": not failures, "failures": failures, "html_files": [p.name for p in html_files]}
