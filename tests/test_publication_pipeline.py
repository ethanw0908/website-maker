from pathlib import Path


def test_generation_attempts_publication_after_qa():
    source = Path("app/tasks.py").read_text(encoding="utf-8")
    assert "settings.auto_publish_after_qa" in source
    assert "publish_generation_job(db, job" in source
    assert "save_publication_failure(db, job, exc)" in source


def test_github_result_survives_vercel_failure():
    source = Path("app/services/publisher.py").read_text(encoding="utf-8")
    assert 'result["vercel_error"] = str(exc)' in source
    assert "return result" in source


def test_deployment_is_persisted_with_partial_publication():
    source = Path("app/services/publication.py").read_text(encoding="utf-8")
    assert 'status="ready" if result.get("preview_url") else "repository_created"' in source
    assert 'build_error=result.get("vercel_error")' in source
    assert "db.add(deployment)" in source


def test_api_loads_publication_overrides():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "uvicorn app.publication_extensions:app" in compose


def test_publication_defaults_remain_explicitly_gated():
    config = Path("app/config.py").read_text(encoding="utf-8")
    assert "auto_publish_after_qa: bool = True" in config
    assert "allow_repository_creation: bool = False" in config
    assert "allow_vercel_deployment: bool = False" in config
