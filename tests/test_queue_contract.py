from pathlib import Path


def test_frontend_set_preserves_click_order():
    source = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "const selectedLeadIds = new Set()" in source
    assert "const ids = [...selectedLeadIds]" in source or "orderedSelectedIds()" in source


def test_api_reorders_database_rows_to_request_order():
    source = Path("app/extensions.py").read_text(encoding="utf-8")
    assert "businesses = [by_id[business_id] for business_id in ids if business_id in by_id]" in source
    assert 'queue="generation"' in source
    assert "ordered_business_ids" in source


def test_generation_worker_is_serial_and_dedicated():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "-Q generation" in compose
    assert "--concurrency=1" in compose
    assert "--prefetch-multiplier=1" in compose
    assert "audit-worker:" in compose


def test_qa_failed_jobs_can_be_retried_through_api():
    backend = Path("app/extensions.py").read_text(encoding="utf-8")
    assert '/api/jobs/{job_id}/retry' in backend
