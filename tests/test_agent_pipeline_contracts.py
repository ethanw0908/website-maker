from pathlib import Path

from app.services.agent_pipeline import AgentPipeline


def test_promote_nested_site_to_workspace_root(tmp_path: Path):
    (tmp_path / "_agent").mkdir()
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html>site</html>", encoding="utf-8")
    (site / "styles.css").write_text("body{}", encoding="utf-8")

    promoted = AgentPipeline._promote_nested_site(tmp_path)

    assert promoted == "site"
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == "<html>site</html>"
    assert (tmp_path / "styles.css").exists()
    assert (tmp_path / "_agent").is_dir()


def test_file_stage_retries_when_codex_does_not_write_required_files(tmp_path: Path):
    pipeline = AgentPipeline()
    agent_dir = tmp_path / "_agent"
    agent_dir.mkdir()
    calls = 0

    def fake_codex(prompt: str, workspace: Path) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            (workspace / "_agent" / "RESEARCH.md").write_text("research", encoding="utf-8")
            (workspace / "_agent" / "SOURCES.json").write_text('{"sources": []}', encoding="utf-8")
        return f"attempt {calls}"

    logs: list[str] = []
    pipeline._run_file_stage(
        stage="research",
        prompt="research now",
        expected=("_agent/RESEARCH.md", "_agent/SOURCES.json"),
        workspace=tmp_path,
        agent_dir=agent_dir,
        run_codex=fake_codex,
        logs=logs,
    )

    assert calls == 2
    assert (agent_dir / "logs" / "research-1.log").exists()
    assert (agent_dir / "logs" / "research-2.log").exists()


def test_builder_recovery_requires_root_index(tmp_path: Path):
    pipeline = AgentPipeline()
    agent_dir = tmp_path / "_agent"
    agent_dir.mkdir()
    calls = 0

    def fake_codex(prompt: str, workspace: Path) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            (workspace / "index.html").write_text("<html>recovered</html>", encoding="utf-8")
        return f"build attempt {calls}"

    diagnostics = pipeline._run_builder(
        prompt="build the site",
        workspace=tmp_path,
        agent_dir=agent_dir,
        run_codex=fake_codex,
        logs=[],
    )

    assert calls == 2
    assert diagnostics == []
    assert (tmp_path / "index.html").exists()
    assert (agent_dir / "logs" / "build-2.log").exists()


def test_builder_prompt_demands_root_index():
    source = Path("prompts/site_generator.md").read_text(encoding="utf-8")
    assert "Create `index.html` DIRECTLY in the current working directory" in source
    assert "Do NOT put the finished site inside `site/`" in source
