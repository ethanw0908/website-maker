from pathlib import Path


def test_codex_exec_uses_current_automation_flags():
    source = Path("app/services/codex.py").read_text(encoding="utf-8")
    assert '"--full-auto"' not in source
    assert '"-a",\n                "never"' in source
    assert '"--sandbox",\n                "workspace-write"' in source
    assert '"sandbox_workspace_write.network_access=true"' in source
