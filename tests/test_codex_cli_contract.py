from pathlib import Path

from app.services.codex import CodexGenerator


def test_codex_exec_uses_current_automation_flags():
    source = Path("app/services/codex.py").read_text(encoding="utf-8")
    assert '"--full-auto"' not in source
    assert '"-a",\n                "never"' in source
    assert '"--sandbox",\n                "workspace-write"' in source
    assert '"sandbox_workspace_write.network_access=true"' in source


def test_codex_child_environment_does_not_receive_deployment_secrets(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "places-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")
    monkeypatch.setenv("VERCEL_TOKEN", "vercel-secret")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("REDIS_URL", "redis://secret")

    env = CodexGenerator._codex_environment()

    assert env["PATH"] == "/usr/local/bin:/usr/bin"
    for secret_name in (
        "ADMIN_API_KEY",
        "GOOGLE_PLACES_API_KEY",
        "GITHUB_TOKEN",
        "VERCEL_TOKEN",
        "SMTP_PASSWORD",
        "DATABASE_URL",
        "REDIS_URL",
        "OPENAI_API_KEY",
    ):
        assert secret_name not in env
