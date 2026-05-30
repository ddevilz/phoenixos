import base64
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_TIMEOUT = 10.0

# Candidate test path patterns for a source file src/foo/bar.py
_TEST_PATTERNS = [
    "tests/unit/test_{stem}.py",
    "tests/test_{stem}.py",
    "test_{stem}.py",
    "tests/unit/{stem}_test.py",
    "tests/{stem}_test.py",
]


class PRDiff(BaseModel):
    diff: str
    changed_files: list[str]
    test_contents: dict[str, str]  # test file path → source


def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Parse 'https://github.com/owner/repo/pull/42' → (owner, repo, 42)."""
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not m:
        raise ValueError(f"Cannot parse PR URL: {pr_url!r}")
    return m.group(1), m.group(2), int(m.group(3))


def _extract_changed_files_from_diff(diff: str) -> list[str]:
    """Parse unified diff headers to extract changed file paths."""
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path and path not in files:
                files.append(path)
    return files


def _candidate_test_paths(source_path: str) -> list[str]:
    """Given src/auth/validator.py return candidate test file paths."""
    stem = re.sub(r"\.py$", "", source_path.split("/")[-1])
    return [p.format(stem=stem) for p in _TEST_PATTERNS]


async def _fetch_diff(owner: str, repo: str, pr_number: int, token: str | None) -> str:
    headers: dict[str, str] = {"Accept": "application/vnd.github.diff"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        r.raise_for_status()
        return r.text


async def _fetch_file_contents(
    owner: str, repo: str, path: str, ref: str, token: str | None
) -> str | None:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
            headers=headers,
            params={"ref": ref},
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return data.get("content")


async def _fetch_pr_head_sha(
    owner: str, repo: str, pr_number: int, token: str | None
) -> str:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        r.raise_for_status()
        return r.json()["head"]["sha"]


async def fetch_and_parse(pr_url: str, token: str | None = None) -> PRDiff:
    """Fetch PR diff + test file contents from GitHub. Raises on network errors."""
    owner, repo, pr_number = _parse_pr_url(pr_url)

    diff, head_sha = await _fetch_diff(owner, repo, pr_number, token), None
    try:
        head_sha = await _fetch_pr_head_sha(owner, repo, pr_number, token)
    except Exception:
        head_sha = "HEAD"

    changed_files = _extract_changed_files_from_diff(diff)

    test_contents: dict[str, str] = {}
    for source_file in changed_files:
        if not source_file.endswith(".py"):
            continue
        for candidate in _candidate_test_paths(source_file):
            try:
                ref = head_sha or "HEAD"
                content = await _fetch_file_contents(owner, repo, candidate, ref, token)
                if content:
                    test_contents[candidate] = content
                    break
            except Exception as exc:
                logger.debug("Could not fetch %s: %s", candidate, exc)

    return PRDiff(diff=diff, changed_files=changed_files, test_contents=test_contents)


def parse_from_raw(diff: str) -> PRDiff:
    """Build a PRDiff from a raw diff string (no GitHub API calls)."""
    changed_files = _extract_changed_files_from_diff(diff)
    return PRDiff(diff=diff, changed_files=changed_files, test_contents={})
