from pathlib import Path

from app.services.guardrails import validate_generated_site


def test_guardrails_reject_placeholder_site(tmp_path: Path):
    (tmp_path / "index.html").write_text("<html><head></head><body>Lorem ipsum</body></html>")
    result = validate_generated_site(tmp_path)
    assert not result["passed"]
    assert any("noindex" in item for item in result["failures"])


def test_guardrails_accept_minimal_reviewable_site(tmp_path: Path):
    (tmp_path / "index.html").write_text('<meta name="robots" content="noindex, nofollow"><a href="tel:+15555555555">Call</a>')
    for name in ("robots.txt", "sitemap.xml", "README.md", "vercel.json"):
        (tmp_path / name).write_text("ok")
    result = validate_generated_site(tmp_path)
    assert result["passed"]
