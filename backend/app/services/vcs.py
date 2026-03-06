"""VCS service — git clone and push operations using gitpython."""
import re
import tempfile
from pathlib import Path

import git  # gitpython
import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Git branch names: allow alphanumeric, hyphens, underscores, forward slashes, dots.
# Disallow anything that could be interpreted as a git flag or shell metacharacter.
_VALID_BRANCH_RE = re.compile(r'^[a-zA-Z0-9._/\-]{1,200}$')


def _validate_branch_name(branch: str) -> None:
    """Raise ValueError if branch contains characters unsafe for git refspecs."""
    if not _VALID_BRANCH_RE.match(branch):
        raise ValueError(
            f"Invalid branch name '{branch}'. Only alphanumeric characters, "
            "hyphens, underscores, dots, and forward slashes are allowed."
        )


def _inject_token(url: str, token: str, provider: str = "github", username: str | None = None) -> str:
    """Inject authentication token into a git HTTPS URL."""
    # Strip any existing credentials
    url = re.sub(r'https?://[^@]+@', 'https://', url)
    if not url.startswith("https://"):
        return url
    host = url[8:]  # strip "https://"
    if provider == "gitlab":
        return f"https://oauth2:{token}@{host}"
    elif provider == "bitbucket":
        user = username or "x-token-auth"
        return f"https://{user}:{token}@{host}"
    else:
        # GitHub and generic: https://token@host/...
        return f"https://{token}@{host}"


def clone_repo(
    repo_url: str,
    dest_dir: str,
    token: str | None = None,
    provider: str = "github",
    username: str | None = None,
    branch: str | None = None,
) -> git.Repo:
    """Clone a git repository into dest_dir."""
    if branch:
        _validate_branch_name(branch)
    clone_url = _inject_token(repo_url, token, provider, username) if token else repo_url
    kwargs: dict = {"to_path": dest_dir}
    if branch:
        kwargs["branch"] = branch
    kwargs["depth"] = 1   # shallow clone for speed
    logger.info("Cloning repo", extra={"url": repo_url, "dest": dest_dir})
    return git.Repo.clone_from(clone_url, **kwargs)


async def test_connection(
    repo_url: str | None,
    token: str,
    provider: str,
    base_url: str | None = None,
) -> tuple[bool, str]:
    """Test that the token is valid by hitting the provider's API."""
    try:
        headers = {}
        api_url = ""
        if provider == "github":
            headers["Authorization"] = f"Bearer {token}"
            headers["Accept"] = "application/vnd.github+json"
            if repo_url:
                # Extract owner/repo from URL
                m = re.search(r'github\.com[:/]([^/]+/[^/.]+)', repo_url)
                if m:
                    api_url = f"https://api.github.com/repos/{m.group(1).replace('.git', '')}"
            if not api_url:
                api_url = "https://api.github.com/user"
        elif provider == "gitlab":
            headers["Authorization"] = f"Bearer {token}"
            host = base_url or "https://gitlab.com"
            api_url = f"{host.rstrip('/')}/api/v4/user"
        elif provider == "bitbucket":
            headers["Authorization"] = f"Bearer {token}"
            api_url = "https://api.bitbucket.org/2.0/user"
        else:
            return True, "Connection test not supported for 'other' provider type."
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url, headers=headers)
        if resp.status_code in (200, 201):
            return True, "Connection successful."
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return False, f"Connection failed: {exc}"


async def create_github_pr(
    repo_url: str,
    token: str,
    base_branch: str,
    head_branch: str,
    title: str,
    body: str,
) -> str | None:
    """Create a GitHub pull request. Returns the PR URL or None."""
    m = re.search(r'github\.com[:/]([^/]+/[^/.]+)', repo_url)
    if not m:
        return None
    repo_path = m.group(1).replace(".git", "")
    api_url = f"https://api.github.com/repos/{repo_path}/pulls"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    payload = {"title": title, "body": body, "head": head_branch, "base": base_branch}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            return resp.json().get("html_url")
    except Exception as exc:
        logger.warning("PR creation failed", extra={"error": str(exc)})
    return None


def push_patches_to_repo(
    repo_url: str,
    token: str,
    provider: str,
    username: str | None,
    patches: list,          # list of Patch ORM objects with .file_path and .patched_content
    branch_name: str,
    commit_message: str,
) -> int:
    """
    Clone the repo, write patched_content for each patch file, commit, and push.
    Returns number of files committed.
    """
    _validate_branch_name(branch_name)
    with tempfile.TemporaryDirectory(prefix="alm_push_") as tmp:
        repo = clone_repo(repo_url, tmp, token=token, provider=provider, username=username)
        # Shallow clones lack full history; unshallow so we can push a new branch.
        if repo.git.rev_parse("--is-shallow-repository").strip() == "true":
            repo.git.fetch("--unshallow")
        # Create and checkout new branch
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()

        changed = 0
        tmp_root = Path(tmp).resolve()
        for patch in patches:
            if not patch.file_path or not patch.patched_content:
                continue
            full_path = (tmp_root / patch.file_path).resolve()
            if not str(full_path).startswith(str(tmp_root) + "/"):
                logger.warning(
                    "Skipping patch with path traversal attempt",
                    extra={"file_path": patch.file_path},
                )
                continue
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(patch.patched_content, encoding="utf-8")
            changed += 1

        if changed == 0:
            return 0

        repo.git.add(A=True)
        repo.index.commit(commit_message)
        auth_url = _inject_token(repo_url, token, provider, username)
        origin = repo.remote("origin")
        origin.set_url(auth_url)
        origin.push(refspec=f"{branch_name}:{branch_name}")
        return changed
