"""
Report Generator
================
Produces JSON and Markdown reports from analysis results.

Reports are written to a ``reports/`` directory (created automatically)
next to the script entry point, with filenames derived from the
repository name.
"""

import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generate JSON and Markdown reports for a single repository analysis.

    Parameters
    ----------
    output_dir : str
        Directory where reports will be saved.
    """

    def __init__(self, output_dir: str = "reports") -> None:
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, analysis: dict) -> tuple[str, str]:
        """
        Write both JSON and Markdown reports for an analysis result.

        Parameters
        ----------
        analysis : dict
            Full analysis payload (repo info, ecosystems, dependencies,
            health score, etc.).

        Returns
        -------
        tuple[str, str]
            Paths to the JSON and Markdown files.
        """
        repo_slug = analysis.get("repository", "unknown").replace("/", "_")
        json_path = os.path.join(self.output_dir, f"{repo_slug}.json")
        md_path = os.path.join(self.output_dir, f"{repo_slug}.md")

        # ---- JSON ----
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False, default=str)
        logger.info("JSON report saved → %s", json_path)

        # ---- Markdown ----
        md = self._render_markdown(analysis)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)
        logger.info("Markdown report saved → %s", md_path)

        return json_path, md_path

    # ------------------------------------------------------------------
    # Markdown rendering
    # ------------------------------------------------------------------
    def _render_markdown(self, a: dict) -> str:
        repo = a.get("repository", "unknown")
        ts = a.get("analyzed_at", datetime.now(timezone.utc).isoformat())
        health = a.get("health", {})
        score = health.get("score", 0)
        risk = health.get("risk_level", "UNKNOWN")
        breakdown = health.get("breakdown", {})
        stats = health.get("summary_stats", {})
        ecosystems = a.get("ecosystems", {})
        deps = a.get("dependencies", [])
        repo_info = a.get("repo_info", {})

        # Risk badge emoji
        badge = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}.get(risk, "⚪")

        lines = [
            f"# 📦 Dependency Analysis Report",
            f"## Repository: `{repo}`",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| **Analyzed At** | {ts} |",
            f"| **Description** | {repo_info.get('description', 'N/A')} |",
            f"| **Stars** | {repo_info.get('stargazers_count', 'N/A'):,} |" if isinstance(repo_info.get('stargazers_count'), int) else f"| **Stars** | N/A |",
            f"| **Primary Language** | {repo_info.get('language', 'N/A')} |",
            f"| **Ecosystems Detected** | {', '.join(ecosystems.keys()) if ecosystems else 'None'} |",
            "",
            "---",
            "",
            f"## 🏥 Health Score: **{score}/100** {badge} {risk}",
            "",
            "### Score Breakdown",
            "",
            "| Criterion | Score |",
            "|-----------|-------|",
            f"| Version Pinning Quality | {breakdown.get('pinning_quality', 0)}/40 |",
            f"| Version Range Tightness | {breakdown.get('range_tightness', 0)}/20 |",
            f"| Dependency Count Risk | {breakdown.get('count_risk', 0)}/15 |",
            f"| Outdated Version Flags | {breakdown.get('outdated_flags', 0)}/15 |",
            f"| Manifest Completeness | {breakdown.get('completeness', 0)}/10 |",
            "",
            "### Summary Statistics",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Dependencies | {stats.get('total_dependencies', 0)} |",
            f"| Production | {stats.get('production_deps', 0)} |",
            f"| Development | {stats.get('dev_deps', 0)} |",
            f"| Pinned | {stats.get('pinned_count', 0)} |",
            f"| Unpinned | {stats.get('unpinned_count', 0)} |",
            f"| Pinning Ratio | {stats.get('pinning_ratio', 0):.1%} |",
            "",
            "---",
            "",
            "## 📋 Dependency List",
            "",
        ]

        if deps:
            lines.append("| # | Package | Version Constraint | Pinning | Dev? | Source |")
            lines.append("|---|---------|-------------------|---------|------|--------|")
            for i, d in enumerate(deps, 1):
                name = d.get("name", "")
                vc = d.get("version_constraint", "") or "*unpinned*"
                pt = d.get("pinning_type", "")
                dev = "✅" if d.get("is_dev") else ""
                src = d.get("source_file", "")
                lines.append(f"| {i} | `{name}` | `{vc}` | {pt} | {dev} | {src} |")
        else:
            lines.append("*No dependencies found.*")

        lines.extend([
            "",
            "---",
            "",
            f"*Generated by [Repo Dependency Analyzer v1.0.0]"
            f" on {ts}*",
        ])

        return "\n".join(lines) + "\n"
