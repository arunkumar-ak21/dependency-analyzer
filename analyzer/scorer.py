"""
Health Scorer
=============
Computes a dependency health score (0–100) and risk level for a
repository based on its parsed dependency data.

Scoring criteria and weights:
    - Version Pinning Quality   (40 pts)
    - Version Range Tightness   (20 pts)
    - Dependency Count Risk     (15 pts)
    - Outdated Dependency Flags (15 pts)
    - Manifest Completeness     (10 pts)
"""

import logging
import re
from .parsers.base import Dependency

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk level thresholds
# ---------------------------------------------------------------------------
RISK_LOW = "LOW"          # score 80–100
RISK_MEDIUM = "MEDIUM"    # score 50–79
RISK_HIGH = "HIGH"        # score 0–49


def compute_risk_level(score: int) -> str:
    if score >= 80:
        return RISK_LOW
    elif score >= 50:
        return RISK_MEDIUM
    return RISK_HIGH


class HealthScorer:
    """
    Calculate a health score for a set of dependencies.

    Usage::

        scorer = HealthScorer()
        result = scorer.score(dependencies, has_lock_file=True)
        print(result["score"], result["risk_level"])
    """

    # Weight allocation (must sum to 100)
    W_PINNING = 40
    W_TIGHTNESS = 20
    W_COUNT = 15
    W_OUTDATED = 15
    W_COMPLETENESS = 10

    # Pinning scores per type (0.0–1.0)
    PINNING_SCORES = {
        "exact": 1.0,
        "compatible": 0.8,
        "range": 0.6,
        "minimum": 0.3,
        "complex": 0.4,
        "unpinned": 0.0,
    }

    def score(
        self,
        dependencies: list[Dependency],
        has_lock_file: bool = False,
        ecosystems_detected: int = 1,
    ) -> dict:
        """
        Compute a health score and detailed breakdown.

        Returns a dict with keys:
            score, risk_level, breakdown, summary_stats
        """
        if not dependencies:
            return {
                "score": 0,
                "risk_level": RISK_HIGH,
                "breakdown": {
                    "pinning_quality": 0,
                    "range_tightness": 0,
                    "count_risk": 0,
                    "outdated_flags": 0,
                    "completeness": 0,
                },
                "summary_stats": {
                    "total_dependencies": 0,
                    "production_deps": 0,
                    "dev_deps": 0,
                    "pinned_count": 0,
                    "unpinned_count": 0,
                    "pinning_ratio": 0.0,
                },
            }

        total = len(dependencies)
        prod_deps = [d for d in dependencies if not d.is_dev]
        dev_deps = [d for d in dependencies if d.is_dev]

        # 1. Pinning Quality (0–40)
        pinning_total = sum(
            self.PINNING_SCORES.get(d.pinning_type, 0.0) for d in dependencies
        )
        pinning_ratio = pinning_total / total
        pinning_score = round(pinning_ratio * self.W_PINNING, 1)

        pinned = sum(1 for d in dependencies if d.pinning_type != "unpinned")
        unpinned = total - pinned

        # 2. Range Tightness (0–20)
        tight_types = {"exact", "compatible"}
        tight_count = sum(1 for d in dependencies if d.pinning_type in tight_types)
        tightness_ratio = tight_count / total
        tightness_score = round(tightness_ratio * self.W_TIGHTNESS, 1)

        # 3. Dependency Count Risk (0–15)
        count_score = self._score_count(total)

        # 4. Outdated / Risky Version Flags (0–15)
        outdated_score = self._score_outdated(dependencies)

        # 5. Manifest Completeness (0–10)
        completeness_score = self._score_completeness(has_lock_file, ecosystems_detected)

        total_score = min(100, max(0, round(
            pinning_score + tightness_score + count_score +
            outdated_score + completeness_score
        )))

        return {
            "score": total_score,
            "risk_level": compute_risk_level(total_score),
            "breakdown": {
                "pinning_quality": pinning_score,
                "range_tightness": tightness_score,
                "count_risk": count_score,
                "outdated_flags": outdated_score,
                "completeness": completeness_score,
            },
            "summary_stats": {
                "total_dependencies": total,
                "production_deps": len(prod_deps),
                "dev_deps": len(dev_deps),
                "pinned_count": pinned,
                "unpinned_count": unpinned,
                "pinning_ratio": round(pinning_ratio, 3),
            },
        }

    # ------------------------------------------------------------------
    # Sub-scoring functions
    # ------------------------------------------------------------------
    def _score_count(self, total: int) -> float:
        """Fewer direct dependencies = healthier. Penalize >100."""
        if total <= 10:
            return self.W_COUNT
        elif total <= 30:
            return self.W_COUNT * 0.9
        elif total <= 60:
            return self.W_COUNT * 0.7
        elif total <= 100:
            return self.W_COUNT * 0.5
        else:
            return self.W_COUNT * 0.3

    def _score_outdated(self, deps: list[Dependency]) -> float:
        """Flag pre-1.0 versions and suspicious patterns."""
        if not deps:
            return self.W_OUTDATED
        flagged = 0
        for d in deps:
            v = d.version_constraint
            if not v:
                continue
            # Pre-1.0 (0.x.y) — potentially unstable
            if re.match(r"[=~^<>]*0\.", v):
                flagged += 1
        if flagged == 0:
            return self.W_OUTDATED
        ratio = flagged / len(deps)
        return round(self.W_OUTDATED * (1 - ratio * 0.6), 1)

    def _score_completeness(self, has_lock: bool, ecosystems: int) -> float:
        """Lock file presence adds confidence."""
        base = self.W_COMPLETENESS * 0.5
        if has_lock:
            base += self.W_COMPLETENESS * 0.5
        return round(base, 1)
