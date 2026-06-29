"""GitHub MCP Server — repo cloning, branching, committing, and PR creation."""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

import httpx
from git import Repo, GitCommandError, InvalidGitRepositoryError, NoSuchPathError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.config import settings


def _tool_noop():
    return lambda f: f


class _MCPStub:
    tool = staticmethod(_tool_noop)
    def run(self): pass


mcp = _MCPStub()

_GH_API = "https://api.github.com"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _open_repo(repo_path: str) -> Repo:
    try:
        return Repo(repo_path)
    except (InvalidGitRepositoryError, NoSuchPathError):
        raise ValueError(f"Not a git repository: {repo_path}")


def _inject_token(url: str) -> str:
    """Embed the GitHub token into an HTTPS URL for authenticated operations."""
    token = settings.github_token
    if token and url.startswith("https://") and "@" not in url:
        url = url.replace("https://", f"https://{token}@", 1)
    return url


def _parse_gh_owner_repo(repo: Repo) -> tuple[str, str]:
    """Extract (owner, repo_name) from the 'origin' remote URL."""
    remote_url = repo.remotes.origin.url
    # Handles both HTTPS and SSH formats
    match = re.search(r"[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
    if not match:
        raise ValueError(f"Cannot parse GitHub owner/repo from URL: {remote_url}")
    return match.group(1), match.group(2)


# ------------------------------------------------------------------
# Tool 1: clone_repo
# ------------------------------------------------------------------

@mcp.tool()
def clone_repo(url: str, job_id: str, branch: str = "main") -> str:
    """Clone a GitHub repository into the job workspace.

    Args:
        url: HTTPS GitHub URL (e.g. https://github.com/owner/repo).
        job_id: Unique migration job identifier; determines the workspace subdirectory.
        branch: Branch to check out after cloning (default: main).

    Returns:
        JSON object with 'repo_path' (str), 'branch' (str), 'commit_sha' (str), 'success' (bool).
    """
    import shutil
    target = settings.workspace_dir / job_id / "repo"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    try:
        authed_url = _inject_token(url)
        repo = Repo.clone_from(authed_url, str(target), branch=branch, depth=1)
        sha = repo.head.commit.hexsha
        return json.dumps({
            "success": True,
            "repo_path": str(target),
            "branch": repo.active_branch.name,
            "commit_sha": sha,
        })
    except GitCommandError as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Tool 2: create_branch
# ------------------------------------------------------------------

@mcp.tool()
def create_branch(repo_path: str, branch_name: str) -> str:
    """Create and check out a new branch in the given repository.

    Args:
        repo_path: Absolute path to the local git repository.
        branch_name: Name of the new branch to create.

    Returns:
        JSON object with 'success' (bool), 'branch' (str), and optional 'error'.
    """
    try:
        repo = _open_repo(repo_path)
        # If branch already exists, just check it out
        if branch_name in [b.name for b in repo.branches]:
            repo.git.checkout(branch_name)
            return json.dumps({"success": True, "branch": branch_name, "note": "branch already existed"})
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()
        return json.dumps({"success": True, "branch": branch_name})
    except (GitCommandError, ValueError) as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Tool 3: commit_changes
# ------------------------------------------------------------------

@mcp.tool()
def commit_changes(
    repo_path: str,
    message: str,
    files: list[str] | None = None,
) -> str:
    """Stage files and create a commit in the repository.

    Args:
        repo_path: Absolute path to the local git repository.
        message: Commit message.
        files: List of relative file paths to stage. If null/empty, stages all changes (git add -A).

    Returns:
        JSON object with 'success' (bool), 'commit_sha' (str), 'branch' (str), and optional 'error'.
    """
    try:
        repo = _open_repo(repo_path)

        if files:
            repo.index.add(files)
        else:
            repo.git.add(A=True)

        if not repo.index.diff("HEAD") and not repo.untracked_files:
            return json.dumps({"success": True, "note": "nothing to commit", "commit_sha": repo.head.commit.hexsha})

        commit = repo.index.commit(message)
        return json.dumps({
            "success": True,
            "commit_sha": commit.hexsha,
            "branch": repo.active_branch.name,
            "message": message,
        })
    except (GitCommandError, ValueError) as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Tool 4: create_pull_request
# ------------------------------------------------------------------

@mcp.tool()
def create_pull_request(
    repo_path: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
) -> str:
    """Push the head branch and open a GitHub pull request.

    Requires GITHUB_TOKEN to be set in the environment / .env file.

    Args:
        repo_path: Absolute path to the local git repository.
        title: PR title.
        body: PR description (markdown supported).
        head_branch: Branch to merge from.
        base_branch: Branch to merge into (default: main).

    Returns:
        JSON object with 'success' (bool), 'pr_url' (str), 'pr_number' (int), and optional 'error'.
    """
    token = settings.github_token
    if not token:
        return json.dumps({"success": False, "error": "GITHUB_TOKEN is not set."})

    try:
        repo = _open_repo(repo_path)
        owner, repo_name = _parse_gh_owner_repo(repo)

        # Push the branch
        origin = repo.remotes.origin
        origin.set_url(_inject_token(origin.url))
        repo.git.push("--set-upstream", "origin", head_branch)

        # Create PR via REST API
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        }
        response = httpx.post(
            f"{_GH_API}/repos/{owner}/{repo_name}/pulls",
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return json.dumps({
            "success": True,
            "pr_url": data["html_url"],
            "pr_number": data["number"],
            "head_branch": head_branch,
            "base_branch": base_branch,
        })
    except httpx.HTTPStatusError as exc:
        return json.dumps({"success": False, "error": f"GitHub API error {exc.response.status_code}: {exc.response.text}"})
    except (GitCommandError, ValueError) as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Tool 5: get_current_branch
# ------------------------------------------------------------------

@mcp.tool()
def get_current_branch(repo_path: str) -> str:
    """Return the currently checked-out branch and latest commit info.

    Args:
        repo_path: Absolute path to the local git repository.

    Returns:
        JSON object with 'branch' (str), 'commit_sha' (str), 'commit_message' (str), 'is_dirty' (bool).
    """
    try:
        repo = _open_repo(repo_path)
        return json.dumps({
            "success": True,
            "branch": repo.active_branch.name,
            "commit_sha": repo.head.commit.hexsha,
            "commit_message": repo.head.commit.message.strip(),
            "is_dirty": repo.is_dirty(untracked_files=True),
        })
    except (GitCommandError, ValueError) as exc:
        return json.dumps({"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
