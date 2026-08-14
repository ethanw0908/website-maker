import json
import shutil
from pathlib import Path
from typing import Callable, Iterable

from app.config import get_settings
from app.services.guardrails import prepare_generated_site, validate_generated_site
from app.services.visual_qa import render_site


RunCodex = Callable[[str, Path], str]
SKIP_SITE_PARTS = {"_agent", "node_modules", ".git"}


class AgentPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _prompt(name: str) -> str:
        return (Path("prompts") / name).read_text(encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _write_stage_log(agent_dir: Path, stage: str, attempt: int, output: str) -> Path:
        log_dir = agent_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{stage}-{attempt}.log"
        path.write_text(output or "(Codex returned no output)\n", encoding="utf-8")
        return path

    @staticmethod
    def _missing_files(workspace: Path, expected: Iterable[str]) -> list[str]:
        missing: list[str] = []
        for relative in expected:
            path = workspace / relative
            if not path.exists() or (path.is_file() and not path.read_text(encoding="utf-8", errors="ignore").strip()):
                missing.append(relative)
        return missing

    def _run_file_stage(
        self,
        *,
        stage: str,
        prompt: str,
        expected: tuple[str, ...],
        workspace: Path,
        agent_dir: Path,
        run_codex: RunCodex,
        logs: list[str],
    ) -> None:
        output = run_codex(prompt, workspace)
        log_path = self._write_stage_log(agent_dir, stage, 1, output)
        logs.append(f"{stage.upper()}\n{output}")
        missing = self._missing_files(workspace, expected)
        if not missing:
            return

        recovery = (
            prompt
            + "\n\nRECOVERY REQUIREMENT:\n"
            + "Your previous run exited successfully but did not create every required output file. "
            + "Do the work now using filesystem write tools; do not merely describe what you would do.\n"
            + "Missing required files:\n- "
            + "\n- ".join(missing)
            + "\nWrite each file at exactly the path shown, relative to the current working directory, and verify it exists before finishing."
        )
        output = run_codex(recovery, workspace)
        log_path = self._write_stage_log(agent_dir, stage, 2, output)
        logs.append(f"{stage.upper()} RECOVERY\n{output}")
        missing = self._missing_files(workspace, expected)
        if missing:
            raise RuntimeError(
                f"{stage} stage completed without required files: {', '.join(missing)}. "
                f"Inspect {log_path.relative_to(workspace)} for the Codex output."
            )

    @staticmethod
    def _merge_into_root(source: Path, destination: Path) -> None:
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            for child in list(source.iterdir()):
                AgentPipeline._merge_into_root(child, destination / child.name)
            try:
                source.rmdir()
            except OSError:
                pass
            return

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        shutil.move(str(source), str(destination))

    @classmethod
    def _promote_nested_site(cls, workspace: Path) -> str | None:
        """Promote a static site created in a child directory to the publishable workspace root."""
        if (workspace / "index.html").exists():
            return None

        candidates: list[Path] = []
        for index in workspace.rglob("index.html"):
            relative_parts = index.relative_to(workspace).parts
            if any(part in SKIP_SITE_PARTS for part in relative_parts):
                continue
            if index.parent == workspace:
                continue
            candidates.append(index.parent)

        if not candidates:
            return None

        site_root = sorted(candidates, key=lambda path: (len(path.relative_to(workspace).parts), str(path)))[0]
        for child in list(site_root.iterdir()):
            if child.name in SKIP_SITE_PARTS:
                continue
            cls._merge_into_root(child, workspace / child.name)

        return str(site_root.relative_to(workspace))

    def _run_builder(
        self,
        *,
        prompt: str,
        workspace: Path,
        agent_dir: Path,
        run_codex: RunCodex,
        logs: list[str],
    ) -> list[str]:
        diagnostics: list[str] = []
        output = run_codex(prompt, workspace)
        log_path = self._write_stage_log(agent_dir, "build", 1, output)
        logs.append("BUILD\n" + output)

        promoted = self._promote_nested_site(workspace)
        if promoted:
            diagnostics.append(f"Promoted generated site from {promoted} to workspace root")
        if (workspace / "index.html").exists():
            return diagnostics

        recovery_prompt = (
            self._prompt("builder_recovery.md")
            .replace("{{GENERATION_PROMPT}}", "")
            .replace("{{PREVIOUS_OUTPUT}}", output[-8_000:])
        )
        output = run_codex(recovery_prompt, workspace)
        log_path = self._write_stage_log(agent_dir, "build", 2, output)
        logs.append("BUILD RECOVERY\n" + output)

        promoted = self._promote_nested_site(workspace)
        if promoted:
            diagnostics.append(f"Promoted recovered site from {promoted} to workspace root")
        if not (workspace / "index.html").exists():
            html_candidates = [
                str(path.relative_to(workspace))
                for path in workspace.rglob("*.html")
                if not any(part in SKIP_SITE_PARTS for part in path.relative_to(workspace).parts)
            ]
            detail = f" HTML found elsewhere: {', '.join(html_candidates[:10])}" if html_candidates else " No HTML files were created."
            raise RuntimeError(
                "Builder exited successfully but did not create index.html in the publishable workspace root."
                + detail
                + f" Inspect {log_path.relative_to(workspace)}."
            )
        return diagnostics

    def _run_design_review(
        self,
        *,
        prompt: str,
        review_path: Path,
        workspace: Path,
        agent_dir: Path,
        run_codex: RunCodex,
        logs: list[str],
        revision: int,
    ) -> dict:
        review_path.unlink(missing_ok=True)
        output = run_codex(prompt, workspace)
        self._write_stage_log(agent_dir, f"review-{revision}", 1, output)
        logs.append(f"REVIEW {revision}\n{output}")
        design = self._read_json(review_path)
        if design and "overall" in design:
            return design

        recovery = (
            prompt
            + "\n\nRECOVERY REQUIREMENT:\n"
            + "Your previous review did not leave a valid `_agent/design_review.json` object containing `overall`. "
            + "Perform the review and write the required JSON file now. Do not edit the website."
        )
        output = run_codex(recovery, workspace)
        log_path = self._write_stage_log(agent_dir, f"review-{revision}", 2, output)
        logs.append(f"REVIEW {revision} RECOVERY\n{output}")
        design = self._read_json(review_path)
        if not design or "overall" not in design:
            raise RuntimeError(
                "Design reviewer did not create valid _agent/design_review.json after recovery. "
                f"Inspect {log_path.relative_to(workspace)}."
            )
        return design

    def run(self, brief: dict, workspace: Path, run_codex: RunCodex) -> dict:
        workspace.mkdir(parents=True, exist_ok=True)
        agent_dir = workspace / "_agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "brief.json").write_text(
            json.dumps(brief, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logs: list[str] = []
        diagnostics: list[str] = []
        research_prompt = self._prompt("research_agent.md").replace(
            "{{BRIEF_JSON}}", json.dumps(brief, indent=2, ensure_ascii=False)
        )
        self._run_file_stage(
            stage="research",
            prompt=research_prompt,
            expected=("_agent/RESEARCH.md", "_agent/SOURCES.json"),
            workspace=workspace,
            agent_dir=agent_dir,
            run_codex=run_codex,
            logs=logs,
        )

        creative_prompt = self._prompt("creative_director.md").replace(
            "{{GENERATION_PROMPT}}", brief.get("generation_prompt") or ""
        )
        self._run_file_stage(
            stage="creative",
            prompt=creative_prompt,
            expected=("_agent/DESIGN.md", "_agent/ASSET_PLAN.md"),
            workspace=workspace,
            agent_dir=agent_dir,
            run_codex=run_codex,
            logs=logs,
        )
        self._run_file_stage(
            stage="assets",
            prompt=self._prompt("asset_director.md"),
            expected=("_agent/ASSET_MANIFEST.json",),
            workspace=workspace,
            agent_dir=agent_dir,
            run_codex=run_codex,
            logs=logs,
        )

        builder_prompt = self._prompt("site_generator.md").replace(
            "{{GENERATION_PROMPT}}", brief.get("generation_prompt") or ""
        )
        diagnostics.extend(
            self._run_builder(
                prompt=builder_prompt,
                workspace=workspace,
                agent_dir=agent_dir,
                run_codex=run_codex,
                logs=logs,
            )
        )

        last_error = ""
        last_qa: dict = {}
        for revision in range(self.settings.max_codex_revisions + 1):
            repairs = prepare_generated_site(workspace, brief)
            technical = validate_generated_site(workspace, brief)
            visual = render_site(workspace)

            review_path = agent_dir / "design_review.json"
            reviewer_prompt = (
                self._prompt("design_reviewer.md")
                .replace("{{QUALITY_THRESHOLD}}", str(self.settings.design_qa_threshold))
                .replace("{{GENERATION_PROMPT}}", brief.get("generation_prompt") or "")
            )
            design = self._run_design_review(
                prompt=reviewer_prompt,
                review_path=review_path,
                workspace=workspace,
                agent_dir=agent_dir,
                run_codex=run_codex,
                logs=logs,
                revision=revision,
            )

            try:
                overall = float(design.get("overall", 0))
            except (TypeError, ValueError):
                overall = 0.0

            failures = list(technical.get("failures") or [])
            failures.extend(visual.get("page_errors") or [])
            failures.extend(
                f"Horizontal overflow at {name}"
                for name, has_overflow in (visual.get("horizontal_overflow") or {}).items()
                if has_overflow
            )
            if overall < self.settings.design_qa_threshold:
                problems = design.get("problems") or []
                detail = "; ".join(str(item) for item in problems[:8])
                failures.append(
                    f"Design review score {overall:.1f} is below "
                    f"{self.settings.design_qa_threshold:.1f}"
                    + (f": {detail}" if detail else "")
                )

            last_qa = {
                "passed": not failures,
                "revision": revision,
                "repairs": repairs,
                "technical": technical,
                "visual": visual,
                "design": design,
                "design_score": overall,
                "diagnostics": diagnostics,
                "stage_logs": str((agent_dir / "logs").relative_to(workspace)),
                "failures": failures,
            }
            if not failures:
                return {
                    "workspace": str(workspace),
                    "revision_count": revision,
                    "qa": last_qa,
                    "generator_log": "\n\n".join(logs)[-20_000:],
                }

            last_error = "; ".join(failures)
            if revision >= self.settings.max_codex_revisions:
                break

            revision_prompt = (
                self._prompt("revision_agent.md")
                .replace("{{FAILURES}}", "\n- ".join(failures))
                .replace("{{DESIGN_REVIEW}}", json.dumps(design, indent=2, ensure_ascii=False))
                .replace("{{GENERATION_PROMPT}}", brief.get("generation_prompt") or "")
            )
            output = run_codex(revision_prompt, workspace)
            self._write_stage_log(agent_dir, f"revision-{revision + 1}", 1, output)
            logs.append(f"REVISION {revision + 1}\n{output}")
            promoted = self._promote_nested_site(workspace)
            if promoted:
                diagnostics.append(f"Promoted revised site from {promoted} to workspace root")

        return {
            "workspace": str(workspace),
            "revision_count": self.settings.max_codex_revisions,
            "qa": last_qa,
            "generator_log": "\n\n".join(logs)[-20_000:],
            "error": last_error,
        }
