import os
import shutil
import subprocess
from pathlib import Path

from app.config import get_settings
from app.services.agent_pipeline import AgentPipeline


CODEX_ENV_ALLOWLIST = {
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "TZ",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "CODEX_HOME",
    "NO_COLOR",
}


class GenerationFailure(RuntimeError):
    def __init__(self, message: str, *, qa: dict | None = None, log: str | None = None) -> None:
        super().__init__(message)
        self.qa = qa or {}
        self.log = log or ""


class CodexGenerator:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _codex_environment() -> dict[str, str]:
        """Pass only non-secret process settings into the autonomous Codex child."""
        env = {key: value for key, value in os.environ.items() if key in CODEX_ENV_ALLOWLIST}
        env.setdefault("HOME", str(Path.home()))
        return env

    def _run_codex(self, prompt: str, workspace: Path) -> str:
        process = subprocess.run(
            [
                "codex",
                "-a",
                "never",
                "exec",
                "--ephemeral",
                "--sandbox",
                "workspace-write",
                "-c",
                "sandbox_workspace_write.network_access=true",
                prompt,
            ],
            cwd=workspace,
            env=self._codex_environment(),
            text=True,
            capture_output=True,
            timeout=1_200,
        )
        log = (process.stdout + "\n" + process.stderr)[-16_000:]
        if process.returncode != 0:
            detail = process.stderr[-8_000:] or process.stdout[-8_000:] or "Codex exited unsuccessfully"
            raise RuntimeError(detail)
        return log

    def generate(self, brief: dict, workspace: Path) -> dict:
        if not shutil.which("codex"):
            raise RuntimeError("Codex CLI is not installed in the controller environment")

        auth_file = self.settings.codex_home / "auth.json"
        if not auth_file.exists():
            raise RuntimeError(
                "Codex OAuth is not connected. Run `docker compose run --rm worker codex --login`, "
                "complete Sign in with ChatGPT, then restart the worker."
            )

        try:
            result = AgentPipeline().run(brief, workspace, self._run_codex)
        except Exception as exc:
            raise GenerationFailure(f"Agent pipeline failed: {exc}") from exc

        if not result.get("qa", {}).get("passed"):
            raise GenerationFailure(
                "Generation failed quality review: " + (result.get("error") or "unknown QA failure"),
                qa=result.get("qa") or {},
                log=result.get("generator_log") or "",
            )
        return result
