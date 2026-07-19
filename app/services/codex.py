import json
import os
import shutil
import subprocess
from pathlib import Path

from app.config import get_settings
from app.services.guardrails import prepare_generated_site, validate_generated_site


class GenerationFailure(RuntimeError):
    def __init__(self, message: str, *, qa: dict | None = None, log: str | None = None) -> None:
        super().__init__(message)
        self.qa = qa or {}
        self.log = log or ""


class CodexGenerator:
    def __init__(self) -> None:
        self.settings = get_settings()

    def generate(self, brief: dict, workspace: Path) -> dict:
        if not shutil.which("codex"):
            raise RuntimeError("Codex CLI is not installed in the controller environment")

        auth_file = self.settings.codex_home / "auth.json"
        if not auth_file.exists():
            raise RuntimeError(
                "Codex OAuth is not connected. Run `docker compose run --rm worker codex --login`, "
                "complete Sign in with ChatGPT, then restart the worker."
            )

        workspace.mkdir(parents=True, exist_ok=True)
        prompt_template = Path("prompts/site_generator.md").read_text(encoding="utf-8")
        prompt = prompt_template.replace("{{BRIEF_JSON}}", json.dumps(brief, indent=2, ensure_ascii=False))
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)

        last_error = ""
        last_log = ""
        last_qa: dict = {}
        for revision in range(self.settings.max_codex_revisions + 1):
            revision_prompt = prompt
            if revision:
                revision_prompt += (
                    "\n\nThe previous attempt failed automated QA. Inspect the current files and correct every "
                    "failure below. Preserve good design work and do not invent facts:\n- "
                    + "\n- ".join(last_qa.get("failures") or [last_error])
                )

            process = subprocess.run(
                ["codex", "exec", "--ephemeral", "--full-auto", revision_prompt],
                cwd=workspace,
                env=env,
                text=True,
                capture_output=True,
                timeout=1_200,
            )
            last_log = (process.stdout + "\n" + process.stderr)[-12_000:]
            if process.returncode != 0:
                last_error = process.stderr[-6_000:] or process.stdout[-6_000:] or "Codex exited unsuccessfully"
                continue

            repairs = prepare_generated_site(workspace, brief)
            last_qa = validate_generated_site(workspace, brief)
            last_qa["repairs"] = repairs
            last_qa["revision"] = revision
            if last_qa["passed"]:
                return {
                    "workspace": str(workspace),
                    "revision_count": revision,
                    "qa": last_qa,
                    "generator_log": last_log,
                }
            last_error = "; ".join(last_qa["failures"])

        message = f"Generation failed after {self.settings.max_codex_revisions + 1} attempt(s): {last_error}"
        raise GenerationFailure(message, qa=last_qa, log=last_log)
