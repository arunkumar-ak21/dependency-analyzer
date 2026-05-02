"""
GitHub API Client
=================
Handles all communication with the GitHub REST API, including:
    - Authenticated and unauthenticated requests
    - Automatic rate-limit detection and exponential backoff
    - Fetching repository metadata and file contents

Usage:
    client = GitHubClient(token="ghp_xxxx")
    contents = client.get_repo_contents("django/django")
"""

import time
import base64
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GITHUB_API_BASE = "https://api.github.com"
MAX_RETRIES = 3
BACKOFF_FACTOR = 2  # seconds — doubles on each retry


class GitHubAPIError(Exception):
    """Raised when a GitHub API call fails after all retries."""


class RateLimitError(GitHubAPIError):
    """Raised specifically when rate limit is exhausted and cannot be waited out."""


class GitHubClient:
    """
    Thin wrapper around the GitHub REST API.

    Parameters
    ----------
    token : str or None
        GitHub Personal Access Token.  If provided, the rate limit
        increases from 60 → 5 000 requests/hour.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "RepoDepAnalyzer/1.0",
        })
        if token:
            self.session.headers["Authorization"] = f"token {token}"
            logger.info("GitHub client initialized with authentication token.")
        else:
            logger.warning(
                "No GitHub token provided — rate limit is 60 req/hour. "
                "Set GITHUB_TOKEN or use --token for higher limits."
            )

    # ------------------------------------------------------------------
    # Core request method with retry + rate-limit handling
    # ------------------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Execute an HTTP request with automatic retry on rate-limit (HTTP 403)
        and transient server errors (HTTP 5xx).

        Raises
        ------
        GitHubAPIError
            After MAX_RETRIES unsuccessful attempts.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, timeout=30, **kwargs)
            except requests.RequestException as exc:
                logger.error("Network error (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
                if attempt == MAX_RETRIES:
                    raise GitHubAPIError(f"Network error after {MAX_RETRIES} attempts: {exc}") from exc
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue

            # ---- Rate limit handling ----
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait = max(reset_ts - int(time.time()), 1)
                if wait > 300:
                    raise RateLimitError(
                        f"Rate limit exceeded. Resets in {wait}s (~{wait // 60} min). "
                        "Provide a GITHUB_TOKEN to increase your quota."
                    )
                logger.warning("Rate limit hit — sleeping %ds until reset…", wait)
                time.sleep(wait + 1)
                continue

            # ---- 404 — valid "not found" ----
            if resp.status_code == 404:
                return resp  # let caller decide how to handle

            # ---- Server errors — retry ----
            if resp.status_code >= 500:
                logger.warning("Server error %d (attempt %d/%d)", resp.status_code, attempt, MAX_RETRIES)
                if attempt == MAX_RETRIES:
                    raise GitHubAPIError(f"GitHub returned {resp.status_code} after {MAX_RETRIES} retries.")
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue

            # ---- Client errors (other than 403-rate-limit and 404) ----
            if resp.status_code >= 400:
                raise GitHubAPIError(
                    f"GitHub API error {resp.status_code}: {resp.json().get('message', resp.text)}"
                )

            return resp

        # Should not be reached, but safety net
        raise GitHubAPIError("Request failed after all retries.")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def get_rate_limit(self) -> dict:
        """Return the current rate-limit status from /rate_limit."""
        resp = self._request("GET", f"{GITHUB_API_BASE}/rate_limit")
        data = resp.json()
        core = data.get("resources", {}).get("core", {})
        return {
            "limit": core.get("limit", 0),
            "remaining": core.get("remaining", 0),
            "reset_utc": time.strftime(
                "%Y-%m-%d %H:%M:%S UTC", time.gmtime(core.get("reset", 0))
            ),
        }

    def get_repo_info(self, repo: str) -> Optional[dict]:
        """
        Fetch basic repository metadata (name, description, stars, language).

        Parameters
        ----------
        repo : str
            Full repository name, e.g. ``"django/django"``.

        Returns
        -------
        dict or None
            Repository metadata dict, or None if the repo doesn't exist.
        """
        resp = self._request("GET", f"{GITHUB_API_BASE}/repos/{repo}")
        if resp.status_code == 404:
            logger.error("Repository '%s' not found.", repo)
            return None
        return resp.json()

    def get_repo_root_contents(self, repo: str) -> Optional[list[dict]]:
        """
        List the files/directories at the root of *repo*.

        Returns a list of dicts with keys ``name``, ``type``, ``path``,
        ``download_url``, etc.  Returns None on 404.
        """
        resp = self._request("GET", f"{GITHUB_API_BASE}/repos/{repo}/contents/")
        if resp.status_code == 404:
            return None
        return resp.json()

    def get_file_content(self, repo: str, path: str) -> Optional[str]:
        """
        Download and decode the UTF-8 text of a single file.

        Uses the Contents API (base64-encoded payload) for files ≤ 1 MB
        and falls back to the raw download URL for larger files.

        Returns None if the file doesn't exist.
        """
        url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}"
        resp = self._request("GET", url)
        if resp.status_code == 404:
            return None

        data = resp.json()

        # If the response is a list, the path is a directory — not a file
        if isinstance(data, list):
            return None

        # Base64-encoded content (standard for files ≤ 1 MB)
        content_b64 = data.get("content")
        if content_b64:
            try:
                return base64.b64decode(content_b64).decode("utf-8", errors="replace")
            except Exception:
                logger.warning("Could not decode base64 content for %s/%s", repo, path)

        # Fallback: download raw
        download_url = data.get("download_url")
        if download_url:
            raw = self.session.get(download_url, timeout=30)
            if raw.status_code == 200:
                return raw.text

        return None

    def get_directory_contents(self, repo: str, path: str) -> Optional[list[dict]]:
        """
        List the files inside a subdirectory of *repo*.

        Returns None on 404.
        """
        url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}"
        resp = self._request("GET", url)
        if resp.status_code == 404:
            return None
        data = resp.json()
        if isinstance(data, list):
            return data
        return None
