"""
PHP Dependency Parser
=====================
Parses ``composer.json`` to extract PHP package dependencies.
"""

import json
import logging
from .base import BaseParser, Dependency

logger = logging.getLogger(__name__)


class PhpParser(BaseParser):
    ecosystem = "php"

    def parse(self, content: str, filename: str) -> list[Dependency]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", filename, exc)
            return []

        deps: list[Dependency] = []
        for section, is_dev in [("require", False), ("require-dev", True)]:
            for name, version in data.get(section, {}).items():
                # Skip PHP itself and extensions
                if name.lower() in ("php",) or name.startswith("ext-"):
                    continue
                constraint = str(version).strip()
                deps.append(Dependency(
                    name=name, version_constraint=constraint,
                    source_file=filename,
                    pinning_type=self._classify_composer(constraint),
                    is_dev=is_dev,
                ))
        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps

    @staticmethod
    def _classify_composer(v: str) -> str:
        v = v.strip()
        if not v or v == "*":
            return "unpinned"
        if v.startswith("^") or v.startswith("~"):
            return "compatible"
        if ">=" in v and "<" in v:
            return "range"
        if ">=" in v or ">" in v:
            return "minimum"
        if v[0].isdigit() and " " not in v and "|" not in v:
            return "exact"
        return "complex"
