"""
CLI Entry Point
===============
Command-line interface for the GitHub Repository Dependency Analyzer.

Usage examples::

    # Single repo
    python -m analyzer django/django

    # With token
    python -m analyzer django/django --token ghp_xxxx

    # Batch mode
    python -m analyzer --batch repos.txt

    # Custom output directory
    python -m analyzer django/django -o my_reports
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

from . import __version__
from .github_client import GitHubClient, GitHubAPIError, RateLimitError
from .detector import EcosystemDetector
from .parsers import PARSER_REGISTRY
from .scorer import HealthScorer
from .reporter import ReportGenerator

logger = logging.getLogger("analyzer")

# ======================================================================
# ANSI colour helpers (for terminal output)
# ======================================================================
_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "cyan": "\033[96m",
    "dim": "\033[2m",
}

def _c(text: str, color: str) -> str:
    """Wrap *text* in ANSI colour codes (no-op on Windows without VT)."""
    return f"{_COLORS.get(color, '')}{text}{_COLORS['reset']}"


# ======================================================================
# Core analysis logic
# ======================================================================
def analyze_repo(client: GitHubClient, repo: str) -> dict:
    """
    Run the full analysis pipeline for a single repository.

    Steps:
        1. Fetch repo metadata
        2. List root directory
        3. Detect ecosystems
        4. Fetch + parse each manifest file
        5. Compute health score
        6. Return structured result dict
    """
    print(f"\n{'='*60}")
    print(f"  {_c('Analyzing:', 'bold')} {_c(repo, 'cyan')}")
    print(f"{'='*60}")

    result = {
        "repository": repo,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "repo_info": {},
        "ecosystems": {},
        "dependencies": [],
        "health": {},
        "errors": [],
    }

    # Step 1: Repo metadata
    print(f"  {_c('→', 'dim')} Fetching repository info…")
    repo_info = client.get_repo_info(repo)
    if repo_info is None:
        msg = f"Repository '{repo}' not found on GitHub."
        result["errors"].append(msg)
        print(f"  {_c('✗', 'red')} {msg}")
        return result

    result["repo_info"] = {
        "name": repo_info.get("full_name", repo),
        "description": repo_info.get("description", ""),
        "language": repo_info.get("language", ""),
        "stargazers_count": repo_info.get("stargazers_count", 0),
        "forks_count": repo_info.get("forks_count", 0),
        "open_issues_count": repo_info.get("open_issues_count", 0),
        "default_branch": repo_info.get("default_branch", "main"),
        "license": (repo_info.get("license") or {}).get("spdx_id", "N/A"),
        "archived": repo_info.get("archived", False),
    }
    print(f"  {_c('✓', 'green')} {result['repo_info']['name']} "
          f"★ {result['repo_info']['stargazers_count']:,}  "
          f"({result['repo_info']['language'] or 'unknown lang'})")

    # Step 2: List root contents
    print(f"  {_c('→', 'dim')} Listing root directory…")
    root_files = client.get_repo_root_contents(repo)
    if root_files is None:
        msg = "Could not list repository root contents."
        result["errors"].append(msg)
        print(f"  {_c('✗', 'red')} {msg}")
        return result

    # Step 3: Detect ecosystems
    print(f"  {_c('→', 'dim')} Detecting ecosystems…")
    detector = EcosystemDetector()
    ecosystems = detector.detect(root_files)
    result["ecosystems"] = ecosystems

    if not ecosystems:
        msg = "No supported dependency manifests found in the repo root."
        result["errors"].append(msg)
        print(f"  {_c('!', 'yellow')} {msg}")
        # Still compute score (will be 0)

    for eco_name, eco_info in ecosystems.items():
        print(f"  {_c('✓', 'green')} Ecosystem: {_c(eco_name.upper(), 'bold')} "
              f"— manifests: {', '.join(eco_info['manifest_files'])}")

    # Step 4: Fetch and parse manifests
    all_deps = []
    any_lock = False

    for eco_name, eco_info in ecosystems.items():
        parser_cls = PARSER_REGISTRY.get(eco_name)
        if not parser_cls:
            logger.warning("No parser for ecosystem '%s'", eco_name)
            continue
        parser = parser_cls()

        if eco_info.get("has_lock_file"):
            any_lock = True

        for manifest in eco_info["manifest_files"]:
            print(f"  {_c('→', 'dim')} Parsing {manifest}…")
            content = client.get_file_content(repo, manifest)
            if content is None:
                msg = f"Could not fetch {manifest}"
                result["errors"].append(msg)
                print(f"  {_c('✗', 'red')} {msg}")
                continue
            try:
                deps = parser.parse(content, manifest)
                all_deps.extend(deps)
                print(f"  {_c('✓', 'green')} Found {len(deps)} dependencies in {manifest}")
            except Exception as exc:
                msg = f"Parser error in {manifest}: {exc}"
                result["errors"].append(msg)
                print(f"  {_c('✗', 'red')} {msg}")
                logger.exception("Parser error for %s/%s", repo, manifest)

    result["dependencies"] = [d.to_dict() for d in all_deps]

    # Step 5: Health score
    print(f"  {_c('→', 'dim')} Computing health score…")
    scorer = HealthScorer()
    health = scorer.score(
        all_deps,
        has_lock_file=any_lock,
        ecosystems_detected=len(ecosystems),
    )
    result["health"] = health

    risk = health["risk_level"]
    risk_color = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red"}.get(risk, "dim")
    print(f"  {_c('★', risk_color)} Health Score: "
          f"{_c(str(health['score']), 'bold')}/100 "
          f"[{_c(risk, risk_color)}]")
    print(f"  {_c('→', 'dim')} {health['summary_stats']['total_dependencies']} total deps, "
          f"{health['summary_stats']['pinned_count']} pinned, "
          f"{health['summary_stats']['unpinned_count']} unpinned")

    return result


# ======================================================================
# Batch analysis
# ======================================================================
def load_batch_file(path: str) -> list[str]:
    """
    Read a batch file and return a list of ``owner/repo`` strings.
    Lines starting with ``#`` and blank lines are skipped.
    """
    repos = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    repos.append(line)
    except FileNotFoundError:
        print(f"{_c('Error:', 'red')} Batch file not found: {path}")
        sys.exit(1)
    return repos


# ======================================================================
# Main
# ======================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="repo-dep-analyzer",
        description=(
            "GitHub Repository Dependency Analyzer — "
            "scans repositories, detects ecosystems, parses dependency "
            "manifests, and generates health reports."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m analyzer django/django\n"
            "  python -m analyzer --batch repos.txt\n"
            "  python -m analyzer django/django --token ghp_xxxx -o reports\n"
        ),
    )
    parser.add_argument(
        "repo",
        nargs="?",
        help="Repository to analyze (format: owner/repo)",
    )
    parser.add_argument(
        "--batch", "-b",
        metavar="FILE",
        help="Path to a text file with one repo per line",
    )
    parser.add_argument(
        "--token", "-t",
        default=os.environ.get("GITHUB_TOKEN", ""),
        help="GitHub Personal Access Token (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--output", "-o",
        default="reports",
        help="Output directory for reports (default: reports)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()

    # ---- Logging setup ----
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # ---- Determine repos to analyze ----
    repos: list[str] = []
    if args.batch:
        repos = load_batch_file(args.batch)
        if not repos:
            print(f"{_c('Error:', 'red')} No repositories found in {args.batch}")
            sys.exit(1)
    elif args.repo:
        repos = [args.repo]
    else:
        parser.print_help()
        sys.exit(1)

    # ---- Validate repo format ----
    for r in repos:
        if "/" not in r or len(r.split("/")) != 2:
            print(f"{_c('Error:', 'red')} Invalid repo format: '{r}'. Use owner/repo")
            sys.exit(1)

    # ---- Init components ----
    client = GitHubClient(token=args.token or None)
    reporter = ReportGenerator(output_dir=args.output)

    # ---- Show rate limit ----
    try:
        rl = client.get_rate_limit()
        print(f"\n{_c('GitHub API Rate Limit:', 'bold')} "
              f"{rl['remaining']}/{rl['limit']} remaining "
              f"(resets {rl['reset_utc']})")
    except GitHubAPIError:
        print(f"{_c('!', 'yellow')} Could not check rate limit.")

    # ---- Banner ----
    print(f"\n{'━'*60}")
    print(f"  {_c('Repository Dependency Analyzer', 'bold')} v{__version__}")
    print(f"  Repos to analyze: {len(repos)}")
    print(f"  Output directory: {os.path.abspath(args.output)}")
    print(f"{'━'*60}")

    # ---- Analyze ----
    results = []
    start_time = time.time()

    for i, repo in enumerate(repos, 1):
        print(f"\n[{i}/{len(repos)}]", end="")
        try:
            analysis = analyze_repo(client, repo)
            json_path, md_path = reporter.generate(analysis)
            print(f"  {_c('📄', 'green')} Reports saved:")
            print(f"     JSON → {json_path}")
            print(f"     MD   → {md_path}")
            results.append(analysis)
        except RateLimitError as exc:
            print(f"\n{_c('✗ Rate limit exhausted:', 'red')} {exc}")
            print("Stopping batch. Re-run later or provide a GITHUB_TOKEN.")
            break
        except GitHubAPIError as exc:
            print(f"\n{_c('✗ API error:', 'red')} {exc}")
            results.append({"repository": repo, "error": str(exc)})
        except Exception as exc:
            print(f"\n{_c('✗ Unexpected error:', 'red')} {exc}")
            logger.exception("Unexpected error analyzing %s", repo)
            results.append({"repository": repo, "error": str(exc)})

    # ---- Summary ----
    elapsed = time.time() - start_time
    print(f"\n{'━'*60}")
    print(f"  {_c('Analysis Complete', 'bold')}")
    print(f"  Repos analyzed : {len(results)}/{len(repos)}")
    print(f"  Time elapsed   : {elapsed:.1f}s")
    print(f"  Reports in     : {os.path.abspath(args.output)}/")
    print(f"{'━'*60}")

    # Print summary table
    if results:
        print(f"\n  {'Repository':<40} {'Score':>6}  {'Risk':<8}  {'Deps':>5}")
        print(f"  {'─'*40} {'─'*6}  {'─'*8}  {'─'*5}")
        for r in results:
            repo = r.get("repository", "?")
            h = r.get("health", {})
            s = h.get("score", "ERR")
            risk = h.get("risk_level", "ERR")
            total = h.get("summary_stats", {}).get("total_dependencies", "?")
            risk_c = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red"}.get(risk, "dim")
            print(f"  {repo:<40} {str(s):>6}  {_c(risk, risk_c):<17}  {str(total):>5}")

    print()
