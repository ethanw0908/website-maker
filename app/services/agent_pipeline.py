import json
from pathlib import Path
from typing import Callable

from app.config import get_settings
from app.services.guardrails import prepare_generated_site, validate_generated_site
from app.services.visual_qa import render_site


RunCodex = Callable[[str, Path], str]


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

    def run(self, brief: dict, workspace: Path, run_codex: RunCodex) -> dict:
        workspace.mkdir(parents=True, exist_ok=True)
        agent_dir = workspace / "_agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "brief.json").write_text(
            json.dumps(brief, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logs: list[str] = []
        research_prompt = self._prompt("research_agent.md").replace(
            "{{BRIEF_JSON}}", json.dumps(brief, indent=2, ensure_ascii=False)
        )
        logs.append("RESEARCH\n" + run_codex(research_prompt, workspace))

        creative_prompt = self._prompt("creative_director.md").replace(
            "{{GENERATION_PROMPT}}", brief.get("generation_prompt") or ""
        )
        logs.append("CREATIVE\n" + run_codex(creative_prompt, workspace))
        logs.append("ASSETS\n" + run_codex(self._prompt("asset_director.md"), workspace))

        builder_prompt = self._prompt("site_generator.md").replace(
            "{{GENERATION_PROMPT}}", brief.get("generation_prompt") or ""
        )
        logs.append("BUILD\n" + run_codex(builder_prompt, workspace))

        last_error = ""
        last_qa: dict = {}
        for revision in range(self.settings.max_codex_revisions + 1):
            repairs = prepare_generated_site(workspace, brief)
            technical = validate_generated_site(workspace, brief)
            visual = render_site(workspace)

            review_path = agent_dir / "design_review.json"
            review_path.unlink(missing_ok=True)
            reviewer_prompt = (
                self._prompt("design_reviewer.md")
                .replace("{{QUALITY_THRESHOLD}}", str(self.settings.design_qa_threshold))
                .replace("{{GENERATION_PROMPT}}", brief.get("generation_prompt") or "")
            )
            try:
                logs.append(f"REVIEW {revision}\n" + run_codex(reviewer_prompt, workspace))
            except Exception as exc:
                logs.append(f"REVIEW {revision} ERROR\n{exc}")
            design = self._read_json(review_path)

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
            logs.append(f"REVISION {revision + 1}\n" + run_codex(revision_prompt, workspace))

        return {
            "workspace": str(workspace),
            "revision_count": self.settings.max_codex_revisions,
            "qa": last_qa,
            "generator_log": "\n\n".join(logs)[-20_000:],
            "error": last_error,
        }
