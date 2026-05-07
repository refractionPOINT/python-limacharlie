"""Core logic for mass rule conversion.

Contains the GitHub crawler, local crawler, conversion pipeline,
and progress display used by the ``dr convert-rules`` command.
"""

from __future__ import annotations

import collections
import json
import os
import random
import re
import shutil
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING
from urllib.error import HTTPError
from urllib.parse import quote as urlquote
from urllib.request import Request, urlopen

import click
import yaml

if TYPE_CHECKING:
    from ..sdk.ai import AI
    from ..sdk.organization import Organization


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RuleFile:
    """A source rule file to be converted."""

    path: str       # Relative path from source root
    content: str    # Raw file content
    filename: str   # Basename


@dataclass
class ConversionResult:
    """Result of converting a single rule."""

    source_path: str
    rule_key: str
    success: bool
    detect: dict[str, Any] | None = None
    respond: list[dict[str, Any]] | Any | None = None
    error: str | None = None
    created_in_hive: bool = False


# ---------------------------------------------------------------------------
# File filtering
# ---------------------------------------------------------------------------

_RULE_EXTENSIONS = frozenset({
    ".yml", ".yaml", ".json", ".sigma", ".spl", ".kql", ".toml",
})

_SKIP_BASENAMES = frozenset({
    "readme.md", "license", "license.md", "license.txt",
    "requirements.txt", "setup.py", "pyproject.toml", "setup.cfg",
    ".gitignore", ".gitattributes",
    "changelog.md", "changelog.txt", "changes.md",
    "contributing.md", "code_of_conduct.md",
    "makefile", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "tox.ini", "poetry.lock", "pipfile", "pipfile.lock",
    "package.json", "package-lock.json", "tsconfig.json",
    ".pre-commit-config.yaml", ".yamllint.yml", ".yamllint.yaml",
    "mkdocs.yml", "mkdocs.yaml",
})

_SKIP_DIRS = frozenset({
    ".github", ".git", ".gitlab", ".circleci",
    "tests", "test", "testing", "ci", "scripts",
    "docs", "doc", "documentation",
    "__pycache__", "node_modules", ".vscode", ".idea",
    "venv", ".venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
})

# When no explicit path is given for GitHub, prefer these directories.
_RULE_DIRS = frozenset({
    "rules", "detections", "sigma", "searches", "queries",
    "detection-rules", "splunk", "detection_rules",
})


def is_rule_file(path: str) -> bool:
    """Return True if *path* looks like a detection rule file."""
    basename = os.path.basename(path).lower()
    if basename in _SKIP_BASENAMES:
        return False

    parts = Path(path).parts
    for part in parts:
        if part.lower() in _SKIP_DIRS:
            return False

    _, ext = os.path.splitext(basename)
    return ext in _RULE_EXTENSIONS


def _has_rule_dir_ancestor(path: str) -> bool:
    """Return True if any ancestor directory is a known rule directory."""
    parts = Path(path).parts
    for part in parts[:-1]:  # exclude filename
        if part.lower() in _RULE_DIRS:
            return True
    return False


# ---------------------------------------------------------------------------
# SSL helper (matches client.py)
# ---------------------------------------------------------------------------

def _create_ssl_context() -> ssl.SSLContext | None:
    try:
        ctx = ssl.create_default_context()
        if hasattr(ssl, "OP_IGNORE_UNEXPECTED_EOF"):
            ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
        return ctx
    except Exception:
        return None


_SSL_CTX = _create_ssl_context()


def _urlopen(req: Request, timeout: int = 30) -> Any:
    if _SSL_CTX is not None:
        return urlopen(req, timeout=timeout, context=_SSL_CTX)
    return urlopen(req, timeout=timeout)


# ---------------------------------------------------------------------------
# GitHub crawler
# ---------------------------------------------------------------------------

class GitHubCrawler:
    """Crawl a GitHub repository for detection rule files."""

    GITHUB_API = "https://api.github.com"

    def __init__(
        self,
        repo: str,
        path: str | None = None,
        ref: str | None = None,
        token: str | None = None,
    ) -> None:
        self._owner, self._repo, url_ref, url_path = self._parse_repo(repo)
        # Explicit CLI flags take priority over URL-derived values.
        self._path = path.strip("/") if path else url_path
        self._ref = ref if ref is not None else url_ref
        self._token = token

    @property
    def display_name(self) -> str:
        parts = f"{self._owner}/{self._repo}"
        if self._path:
            parts += f"/{self._path}"
        if self._ref:
            parts += f" @ {self._ref}"
        return parts

    # -- URL parsing --------------------------------------------------------

    @staticmethod
    def _parse_repo(raw: str) -> tuple[str, str, str | None, str | None]:
        """Parse ``owner/repo`` (and optional ref/path) from various URL forms.

        Handles URLs like:
            ``SigmaHQ/sigma``
            ``https://github.com/SigmaHQ/sigma``
            ``https://github.com/SigmaHQ/sigma/tree/master/rules/network``

        Returns:
            (owner, repo, ref_or_none, path_or_none)
        """
        raw = raw.strip().rstrip("/")
        # Strip trailing .git
        if raw.endswith(".git"):
            raw = raw[:-4]
        # Strip protocol and host
        for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                break
        parts = raw.split("/")
        if len(parts) < 2:
            raise ValueError(
                f"Cannot parse GitHub repo from {raw!r}. "
                "Expected owner/repo or https://github.com/owner/repo."
            )
        owner, repo = parts[0], parts[1]
        ref: str | None = None
        path: str | None = None
        # Remainder after owner/repo may be /tree/<ref>[/<path>]
        # or /blob/<ref>[/<path>].
        rest = parts[2:]
        if rest and rest[0] in ("tree", "blob") and len(rest) >= 2:
            ref = rest[1]
            if len(rest) > 2:
                path = "/".join(rest[2:])
        return owner, repo, ref, path

    # -- HTTP helpers -------------------------------------------------------

    def _api_get(self, endpoint: str, timeout: int = 30) -> Any:
        """GET a GitHub API endpoint, returning parsed JSON."""
        url = f"{self.GITHUB_API}{endpoint}"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "limacharlie-cli",
        }
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        req = Request(url, headers=headers)
        try:
            resp = _urlopen(req, timeout=timeout)
            try:
                data = json.loads(resp.read().decode())
            finally:
                resp.close()
            return data
        except HTTPError as e:
            body = e.read().decode() if hasattr(e, "read") else str(e)
            if e.code == 403 and "rate limit" in body.lower():
                raise RuntimeError(
                    "GitHub API rate limit exceeded. "
                    "Pass --github-token or set the GH_TOKEN environment variable."
                ) from e
            if e.code == 404:
                raise RuntimeError(
                    f"GitHub repo not found: {self._owner}/{self._repo}. "
                    "If the repo is private, pass --github-token."
                ) from e
            raise RuntimeError(f"GitHub API error {e.code}: {body}") from e

    def _fetch_raw(self, file_path: str, timeout: int = 30) -> str | None:
        """Fetch file content from raw.githubusercontent.com."""
        if self._ref is None:
            raise RuntimeError("Cannot fetch raw content without a resolved ref")
        # URL-encode the ref (branch names can contain /) and file path segments
        encoded_ref = urlquote(self._ref, safe="")
        encoded_path = "/".join(urlquote(seg, safe="") for seg in file_path.split("/"))
        url = (
            f"https://raw.githubusercontent.com/"
            f"{urlquote(self._owner, safe='')}/{urlquote(self._repo, safe='')}/"
            f"{encoded_ref}/{encoded_path}"
        )
        headers: dict[str, str] = {"User-Agent": "limacharlie-cli"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        req = Request(url, headers=headers)
        try:
            resp = _urlopen(req, timeout=timeout)
            try:
                content = resp.read()
            finally:
                resp.close()
            # Skip binary files (contain null bytes)
            if b"\x00" in content:
                return None
            return content.decode("utf-8", errors="replace")
        except HTTPError:
            return None

    # -- Crawling -----------------------------------------------------------

    def crawl(self, progress_echo: Callable[[str], None] | None = None) -> list[RuleFile]:
        """Crawl the repository and return matching rule files.

        Args:
            progress_echo: Optional callable for status messages.
        """
        def _echo(msg: str) -> None:
            if progress_echo:
                progress_echo(msg)

        # Resolve default branch if no ref given
        if self._ref is None:
            _echo("Resolving default branch...")
            repo_info = self._api_get(f"/repos/{self._owner}/{self._repo}")
            self._ref = repo_info["default_branch"]
            _echo(f"Using branch: {self._ref}")

        # Fetch the full recursive tree (single API call)
        _echo("Fetching repository tree...")
        encoded_ref = urlquote(self._ref, safe="")
        tree_data = self._api_get(
            f"/repos/{self._owner}/{self._repo}/git/trees/{encoded_ref}?recursive=1",
            timeout=60,
        )

        if tree_data.get("truncated"):
            _echo("Repository tree is very large, falling back to contents API...")
            return self._crawl_contents_api(progress_echo=progress_echo)

        # Filter to rule files
        candidates: list[str] = []
        for entry in tree_data.get("tree", []):
            if entry.get("type") != "blob":
                continue
            path = entry["path"]
            if self._path and not path.startswith(self._path + "/") and path != self._path:
                continue
            if is_rule_file(path):
                candidates.append(path)

        # When no explicit path given, try to narrow down to rule directories
        if not self._path and candidates:
            in_rule_dirs = [p for p in candidates if _has_rule_dir_ancestor(p)]
            if in_rule_dirs:
                candidates = in_rule_dirs

        if not candidates:
            return []

        _echo(f"Found {len(candidates)} rule file(s), fetching content...")

        # Fetch content in parallel
        rule_files: list[RuleFile] = []
        lock = threading.Lock()

        def _fetch_one(path: str) -> RuleFile | None:
            content = self._fetch_raw(path)
            if content and content.strip():
                return RuleFile(path=path, content=content, filename=os.path.basename(path))
            return None

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_fetch_one, p): p for p in candidates}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    with lock:
                        rule_files.append(result)

        return rule_files

    _MAX_CONTENTS_API_CALLS = 500  # safety limit to avoid runaway crawling

    def _crawl_contents_api(self, progress_echo: Callable[[str], None] | None = None) -> list[RuleFile]:
        """Fallback: crawl using the Contents API directory-by-directory."""
        start_path = self._path or ""
        rule_files: list[RuleFile] = []
        dirs_to_visit: collections.deque[str] = collections.deque([start_path])
        api_calls = 0

        while dirs_to_visit and api_calls < self._MAX_CONTENTS_API_CALLS:
            current = dirs_to_visit.popleft()
            encoded_current = "/".join(
                urlquote(seg, safe="") for seg in current.split("/")
            ) if current else ""
            endpoint = f"/repos/{self._owner}/{self._repo}/contents/{encoded_current}"
            if self._ref:
                endpoint += f"?ref={urlquote(self._ref, safe='')}"
            api_calls += 1
            try:
                entries = self._api_get(endpoint)
            except RuntimeError:
                continue

            if not isinstance(entries, list):
                entries = [entries]

            for entry in entries:
                if entry["type"] == "dir":
                    dir_name = os.path.basename(entry["path"]).lower()
                    if dir_name not in _SKIP_DIRS:
                        dirs_to_visit.append(entry["path"])
                elif entry["type"] == "file":
                    if is_rule_file(entry["path"]):
                        content = self._fetch_raw(entry["path"])
                        if content and content.strip():
                            rule_files.append(
                                RuleFile(
                                    path=entry["path"],
                                    content=content,
                                    filename=entry["name"],
                                )
                            )

        return rule_files


# ---------------------------------------------------------------------------
# Local crawler
# ---------------------------------------------------------------------------

class LocalCrawler:
    """Crawl a local directory for detection rule files."""

    def __init__(self, directory: str) -> None:
        self._dir = Path(directory).resolve()

    def crawl(self) -> list[RuleFile]:
        rule_files: list[RuleFile] = []
        for root, dirs, files in os.walk(self._dir):
            # Prune skipped directories in-place
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
            for fname in files:
                if fname.startswith("."):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, self._dir)
                if not is_rule_file(rel):
                    continue
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if content.strip():
                        rule_files.append(RuleFile(path=rel, content=content, filename=fname))
                except OSError:
                    continue
        return rule_files


# ---------------------------------------------------------------------------
# Conversion pipeline
# ---------------------------------------------------------------------------

class ConversionPipeline:
    """Convert rules using the LC AI API with parallel workers."""

    def __init__(
        self,
        org: Organization,
        parallel: int = 10,
        prefix: str = "",
    ) -> None:
        from ..sdk.ai import AI
        self._ai = AI(org)
        self._parallel = parallel
        self._prefix = prefix
        self._lock = threading.Lock()
        self._key_counts: dict[str, int] = {}

    def convert_all(
        self,
        rule_files: list[RuleFile],
        progress_callback: Callable[[int, int, int, str], None] | None = None,
    ) -> list[ConversionResult]:
        """Convert all rule files in parallel.

        Args:
            rule_files: List of source rules.
            progress_callback: Called with (completed, total, failed, current_file)
                after each rule finishes.

        Returns:
            list[ConversionResult]: Results for every input rule.
        """
        total = len(rule_files)
        completed = 0
        failed = 0
        results: list[ConversionResult] = []

        # Prime the JWT before spawning workers so that parallel threads
        # don't all independently trigger an OAuth token refresh.
        self._ai.client.refresh_jwt()

        # Pre-allocate keys so that exception handlers don't double-allocate.
        pre_keys = {id(rf): self._unique_key(rf.filename) for rf in rule_files}

        interrupted = False
        try:
            with ThreadPoolExecutor(max_workers=self._parallel) as pool:
                future_to_rule = {
                    pool.submit(self._convert_one_with_retry, rf, pre_keys[id(rf)]): rf
                    for rf in rule_files
                }
                for future in as_completed(future_to_rule):
                    rf = future_to_rule[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = ConversionResult(
                            source_path=rf.path,
                            rule_key=pre_keys[id(rf)],
                            success=False,
                            error=str(exc),
                        )
                    with self._lock:
                        results.append(result)
                        completed += 1
                        if not result.success:
                            failed += 1
                    if progress_callback:
                        progress_callback(completed, total, failed, rf.path)
        except KeyboardInterrupt:
            interrupted = True

        if interrupted:
            click.echo("\nInterrupted — returning partial results.", err=True)

        return results

    _TRANSIENT_RETRIES = 4
    _TRANSIENT_BASE_WAIT = 15  # seconds

    @staticmethod
    def _is_transient_error(error: str) -> bool:
        """Return True if the error looks transient and worth retrying."""
        low = error.lower()
        # Rate limits (429).
        if "rate limit" in low:
            return True
        # Server-side failures (500): timeouts, processing errors, etc.
        if "api error (500)" in low or "api error (502)" in low or "api error (503)" in low:
            return True
        return False

    def _convert_one_with_retry(self, rule_file: RuleFile, key: str | None = None) -> ConversionResult:
        """Call ``_convert_one`` with pipeline-level retries for transient errors.

        The underlying ``Client.request`` already retries 429s and 504s a few
        times, but with many parallel workers the thundering-herd effect can
        exhaust those retries.  Server-side 500s (MCP timeouts, processing
        failures) are also transient.  This wrapper adds additional backoff
        with jitter at the pipeline level so that transient failures don't
        become permanent.
        """
        last_result: ConversionResult | None = None
        for attempt in range(1, self._TRANSIENT_RETRIES + 1):
            result = self._convert_one(rule_file, key)
            if result.success:
                return result
            last_result = result
            if result.error and self._is_transient_error(result.error):
                wait = self._TRANSIENT_BASE_WAIT * attempt + random.uniform(0, 5)
                time.sleep(wait)
                continue
            # Non-transient failure — don't retry.
            return result

        # All retries exhausted — return the last failure.
        return last_result  # type: ignore[return-value]

    def _convert_one(self, rule_file: RuleFile, key: str | None = None) -> ConversionResult:
        """Convert a single rule file.

        Args:
            rule_file: The source rule.
            key: Pre-allocated hive key (from convert_all). Falls back to
                generating one if not provided.
        """
        if key is None:
            key = self._unique_key(rule_file.filename)

        try:
            # Detection prompt
            detect_prompt = (
                f"Convert this detection rule to LimaCharlie D&R detection format:\n\n"
                f"{rule_file.content}"
            )
            detect_resp = self._ai.generate_detection(detect_prompt)
            detect_data = self._parse_ai_response(detect_resp)

            # Response prompt (includes detection for context)
            detect_yaml_str = yaml.dump(detect_data, default_flow_style=False) if isinstance(detect_data, dict) else str(detect_data)
            respond_prompt = (
                f"Generate a LimaCharlie D&R response for this detection rule:\n\n"
                f"{rule_file.content}\n\n"
                f"The detection component is:\n{detect_yaml_str}"
            )
            respond_resp = self._ai.generate_response(respond_prompt)
            respond_data = self._parse_ai_response(respond_resp)

            # Normalize types
            if isinstance(detect_data, str):
                detect_data = yaml.safe_load(detect_data)
            if isinstance(respond_data, str):
                respond_data = yaml.safe_load(respond_data)
            if isinstance(respond_data, dict):
                respond_data = [respond_data]

            # Validate detect_data is a dict (yaml.safe_load can return None or a scalar)
            if not isinstance(detect_data, dict):
                return ConversionResult(
                    source_path=rule_file.path,
                    rule_key=key,
                    success=False,
                    error=f"AI returned non-dict detection: {type(detect_data).__name__}",
                )

            return ConversionResult(
                source_path=rule_file.path,
                rule_key=key,
                success=True,
                detect=detect_data,
                respond=respond_data,
            )
        except Exception as exc:
            return ConversionResult(
                source_path=rule_file.path,
                rule_key=key,
                success=False,
                error=str(exc),
            )

    @staticmethod
    def _parse_ai_response(resp: dict[str, Any]) -> Any:
        """Extract the useful payload from an AI SDK response."""
        if isinstance(resp, dict):
            if "response" in resp:
                return resp["response"]
            for key in ("detection", "respond", "yaml", "content", "result"):
                if key in resp:
                    return resp[key]
        return resp

    def _unique_key(self, filename: str) -> str:
        """Generate a unique hive key from a filename."""
        base = self._sanitize_key(filename)
        with self._lock:
            count = self._key_counts.get(base, 0)
            self._key_counts[base] = count + 1
            if count == 0:
                return base
            return f"{base}-{count + 1}"

    def _sanitize_key(self, filename: str) -> str:
        """Convert a filename to a valid hive key name."""
        name = os.path.splitext(filename)[0]
        name = name.lower()
        name = re.sub(r"[^a-z0-9]+", "-", name)
        name = name.strip("-")
        if not name:
            name = "rule"
        if self._prefix:
            safe_prefix = re.sub(r"[^a-z0-9]+", "-", self._prefix.lower()).strip("-")
            if safe_prefix:
                name = f"{safe_prefix}-{name}"
        return name


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

class ProgressDisplay:
    """Terminal progress display for batch conversion."""

    def __init__(self, total: int, quiet: bool = False) -> None:
        self._total = total
        self._quiet = quiet
        self._start = time.monotonic()
        self._lock = threading.Lock()

    def update(self, completed: int, total: int, failed: int, current_file: str = "") -> None:
        """Update the progress line in-place."""
        if self._quiet:
            return
        with self._lock:
            elapsed = time.monotonic() - self._start
            eta = ""
            if completed > 0:
                remaining = (elapsed / completed) * (total - completed)
                eta = f" | ETA: {self._fmt_duration(remaining)}"

            line = f"\rConverting: [{completed}/{total}]"
            if failed > 0:
                line += f" {failed} failed"
            line += eta

            term_width = shutil.get_terminal_size((80, 24)).columns
            # Pad to overwrite previous longer line, but stay within terminal
            click.echo(line.ljust(term_width)[:term_width], nl=False)

    def finish(self, results: list[ConversionResult]) -> None:
        """Print the final summary after conversion."""
        if self._quiet:
            return

        click.echo()  # end the progress line

        elapsed = time.monotonic() - self._start
        succeeded = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        hive_created = [r for r in results if r.created_in_hive]

        click.echo(f"\nConversion complete ({self._fmt_duration(elapsed)})")
        click.echo("-" * 40)
        click.echo(f"  Total rules:       {len(results)}")
        click.echo(f"  Converted:         {len(succeeded)}")
        click.echo(f"  Failed:            {len(failed)}")
        click.echo(f"  Created in hive:   {len(hive_created)}")

        if failed:
            click.echo(f"\nFailed rules:")
            for r in failed:
                click.echo(f"  {r.source_path}: {r.error}", err=True)

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s}s"
        m, s = divmod(s, 60)
        if m < 60:
            return f"{m}m {s}s"
        h, m = divmod(m, 60)
        return f"{h}h {m}m"
