import re
import shutil
import subprocess
from pathlib import Path

import httpx

from app.config import get_settings


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:70] or "business"


def repository_name(business_name: str, city: str | None) -> str:
    return f"concept-{slugify(business_name)}-{slugify(city or 'local')}"


class Publisher:
    def __init__(self) -> None:
        self.settings = get_settings()

    def publish(self, workspace: Path, business_name: str, city: str | None, visibility: str, deploy: bool) -> dict:
        if not self.settings.allow_repository_creation:
            raise RuntimeError("Repository creation is disabled. Set ALLOW_REPOSITORY_CREATION=true.")
        if not self.settings.github_token:
            raise RuntimeError("GITHUB_TOKEN is required")
        if not shutil.which("git"):
            raise RuntimeError("git is not installed")

        repo_name = repository_name(business_name, city)
        repo = self._create_repository(repo_name, visibility)
        self._push_repository(workspace, repo["clone_url"])
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip()
        result = {
            "github_repository": repo["html_url"],
            "github_owner": repo["owner"]["login"],
            "commit_sha": commit_sha,
        }

        if deploy:
            try:
                result.update(self.deploy_workspace(workspace, repo_name))
            except RuntimeError as exc:
                # GitHub publication succeeded. Preserve that result and report Vercel separately.
                result["vercel_error"] = str(exc)
        return result

    def deploy_workspace(self, workspace: Path, project_name: str) -> dict:
        if not self.settings.allow_vercel_deployment:
            raise RuntimeError("Vercel deployment is disabled. Set ALLOW_VERCEL_DEPLOYMENT=true.")
        if not shutil.which("vercel") or not self.settings.vercel_token:
            raise RuntimeError("Vercel CLI and VERCEL_TOKEN are required")
        command = ["vercel", "--yes", "--token", self.settings.vercel_token, "--name", project_name]
        process = subprocess.run(command, cwd=workspace, text=True, capture_output=True, timeout=600)
        if process.returncode != 0:
            raise RuntimeError(process.stderr[-4_000:] or process.stdout[-4_000:] or "Vercel deployment failed")
        preview_url = next(
            (line.strip() for line in reversed(process.stdout.splitlines()) if line.strip().startswith("http")),
            None,
        )
        if not preview_url:
            raise RuntimeError("Vercel completed without returning a preview URL")
        return {"preview_url": preview_url, "vercel_output": process.stdout[-4_000:]}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _create_repository(self, name: str, visibility: str) -> dict:
        headers = self._headers()
        payload = {
            "name": name,
            "private": visibility == "private",
            "description": "Private LocalSite Agent concept preview",
        }
        with httpx.Client(timeout=30) as client:
            identity = client.get("https://api.github.com/user", headers=headers)
            identity.raise_for_status()
            authenticated_owner = identity.json()["login"]
            owner = (self.settings.github_organization or authenticated_owner).strip()

            endpoint = f"https://api.github.com/orgs/{owner}/repos" if self.settings.github_organization else "https://api.github.com/user/repos"
            response = client.post(endpoint, headers=headers, json=payload)
            if response.status_code == 422:
                lookup = client.get(f"https://api.github.com/repos/{owner}/{name}", headers=headers)
                lookup.raise_for_status()
                return lookup.json()
            if response.status_code in {403, 404} and self.settings.github_organization:
                raise RuntimeError(
                    f"GitHub could not create a repository in organization '{owner}'. Confirm the token owner is an "
                    "organization member and the token has repository Administration write permission."
                )
            response.raise_for_status()
            return response.json()

    def _push_repository(self, workspace: Path, clone_url: str) -> None:
        git_dir = workspace / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)
        subprocess.run(["git", "init", "-b", "main"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.name", "LocalSite Agent"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.email", "localsite-agent@users.noreply.github.com"], cwd=workspace, check=True)
        subprocess.run(["git", "add", "."], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-m", "Create reviewed concept website"], cwd=workspace, check=True)
        authenticated = clone_url.replace("https://", f"https://x-access-token:{self.settings.github_token}@")
        subprocess.run(["git", "remote", "add", "origin", authenticated], cwd=workspace, check=True)
        try:
            subprocess.run(["git", "push", "--force", "-u", "origin", "main"], cwd=workspace, check=True)
        finally:
            subprocess.run(["git", "remote", "set-url", "origin", clone_url], cwd=workspace, check=False)
