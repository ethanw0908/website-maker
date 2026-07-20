from pathlib import Path

from app.services.guardrails import prepare_generated_site, validate_generated_site


def write_site(root: Path, robots: str = "nofollow, noindex") -> None:
    for name in ("index.html", "about.html", "services.html", "contact.html"):
        root.joinpath(name).write_text(
            f"<html><head><meta content='{robots}' name='robots'></head><body>"
            "<p>Unofficial concept preview</p><a href='tel:+15555555555'>Call</a></body></html>",
            encoding="utf-8",
        )


def test_guardrails_accept_flexible_robots_metadata_and_disclaimer(tmp_path: Path):
    write_site(tmp_path)
    prepare_generated_site(tmp_path, {"company": {"phone": "+15555555555"}})
    result = validate_generated_site(tmp_path, {"company": {"phone": "+15555555555"}})
    assert result["passed"]


def test_guardrails_do_not_require_contact_when_none_is_verified(tmp_path: Path):
    write_site(tmp_path)
    for path in tmp_path.glob("*.html"):
        path.write_text(path.read_text().replace("<a href='tel:+15555555555'>Call</a>", ""))
    prepare_generated_site(tmp_path, {"company": {}})
    result = validate_generated_site(tmp_path, {"company": {}})
    assert result["passed"]
    assert any("contact-link QA was skipped" in warning for warning in result["warnings"])


def test_prepare_generated_site_creates_safe_support_files(tmp_path: Path):
    write_site(tmp_path, robots="index, follow")
    repairs = prepare_generated_site(tmp_path, {"company": {"phone": "+15555555555"}})
    result = validate_generated_site(tmp_path, {"company": {"phone": "+15555555555"}})
    assert result["passed"]
    assert set(("robots.txt", "sitemap.xml", "README.md", "vercel.json")).issubset(
        {path.name for path in tmp_path.iterdir()}
    )
    assert repairs
