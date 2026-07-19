import re
import shutil
import subprocess
from pathlib import Path

import httpx

from app.config import get_settings


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:70] or "business"


class Publisher:
    def __init__(self) -> None:
        self.settings = get_settings()

    def publish(self, workspace: Path, business_name: str, city: str | None, visibility: str, deploy: bool) -> dict:
        if not self.settings.allow_repository_creation:
            raise RuntimeError("Repository creation is disabled. Set ALLOW_REPOSITORY_CREATION=true after review.")
        if not self.settings.github_token:
            raise RuntimeError("GITHUB_TOKEN is required")
        if not shutil.which("git"):
            raise RuntimeError("git is not installed")

        repo_name = f"concept-{slugify(business_name)}-{slugify(city or 'local')}"
        repo = self._create_repository(repo_name, visibility)
        self._push_repository(workspace, repo["clone_url"])
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()
        result = {"github_repository": repo["html_url"], "commit_sha": commit_sha}

        if deploy:
            if not self.settings.allow_vercel_deployment:
                raise RuntimeError("Vercel deployment is disabled. Set ALLOW_VERCEL_DEPLOYMENT=true after review.")
            result.update(self._deploy_vercel(workspace, repo_name))
        return result

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _create_repository(self, name: str, visibility: str) -> dict:
        headers = self._headers()
        payload = {"name": name, "private": visibility == "private", "description": "Private LocalSite Agent concept preview"}
        with httpx.Client(timeout=30) as client:
            identity = client.get("https://api.github.com/user", headers=headers)
            identity.raise_for_status()
            owner = identity.json()["login"]

            response = client.post("https://api.github.com/user/repos", headers=headers, json=payload)
            if response.status_code == 422:
                lookup = client.get(f"https://api.github.com/repos/{owner}/{name}", headers=headers)
                lookup.raise_for_status()
                return lookup.json()
            response.raise_for_status()
            return response.json()

    def _push_repository(self, workspace: Path, clone_url: str) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.name", "LocalSite Agent"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.email", "localsite-agent@users.noreply.github.com"], cwd=workspace, check=True)
        subprocess.run(["git", "add", "."], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-m", "Create reviewed concept website"], cwd=workspace, check=True)
        authenticated = clone_url.replace("https://", f"https://x-access-token:{self.settings.github_token}@")
        subprocess.run(["git", "remote", "add", "origin", authenticated], cwd=workspace, check=True)
        try:
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd=workspace, check=True)
        finally:
            subprocess.run(["git", "remote", "set-url", "origin", clone_url], cwd=workspace, check=False)

    def _deploy_vercel(self, workspace: Path, project_name: str) -> dict:
        if not shutil.which("vercel") or not self.settings.vercel_token:
            raise RuntimeError("Vercel CLI and VERCEL_TOKEN are required")
        command = ["vercel", "--yes", "--token", self.settings.vercel_token, "--name", project_name]
        process = subprocess.run(command, cwd=workspace, text=True, capture_output=True, timeout=600)
        if process.returncode != 0:
            raise RuntimeError(process.stderr[-4_000:] or "Vercel deployment failed")
        preview_url = next((line.strip() for line in reversed(process.stdout.splitlines()) if line.strip().startswith("http")), None)
        return {"preview_url": preview_url, "vercel_output": process.stdout[-4_000:]}
