import json
import os
import shutil
import subprocess
from pathlib import Path

from app.config import get_settings
from app.services.guardrails import validate_generated_site


class CodexGenerator:
    def __init__(self) -> None:
        self.settings = get_settings()

    def generate(self, brief: dict, workspace: Path) -> dict:
        if not shutil.which("codex"):
            raise RuntimeError("Codex CLI is not installed in the controller environment")
        workspace.mkdir(parents=True, exist_ok=True)
        prompt_template = Path("prompts/site_generator.md").read_text(encoding="utf-8")
        prompt = prompt_template.replace("{{BRIEF_JSON}}", json.dumps(brief, indent=2, ensure_ascii=False))
        env = os.environ.copy()
        if self.settings.openai_api_key:
            env["OPENAI_API_KEY"] = self.settings.openai_api_key

        last_error = None
        for revision in range(self.settings.max_codex_revisions + 1):
            revision_prompt = prompt if revision == 0 else (
                prompt + "\n\nThe previous attempt failed QA. Correct every issue below without inventing facts:\n" + last_error
            )
            process = subprocess.run(
                ["codex", "exec", "--ephemeral", "--full-auto", revision_prompt],
                cwd=workspace,
                env=env,
                text=True,
                capture_output=True,
                timeout=1_200,
            )
            if process.returncode != 0:
                last_error = process.stderr[-6_000:] or process.stdout[-6_000:]
                continue
            qa = validate_generated_site(workspace)
            if qa["passed"]:
                return {"workspace": str(workspace), "revision_count": revision, "qa": qa}
            last_error = "\n".join(qa["failures"])

        raise RuntimeError(f"Generation failed after allowed revisions: {last_error}")
