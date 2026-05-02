"""
Ruby Dependency Parser
======================
Parses ``Gemfile`` to extract gem dependencies.
"""

import re
import logging
from .base import BaseParser, Dependency

logger = logging.getLogger(__name__)


class RubyParser(BaseParser):
    ecosystem = "ruby"

    _GEM_LINE = re.compile(
        r"""^\s*gem\s+['"]([^'"]+)['"]"""
        r"""(?:\s*,\s*['"]([^'"]+)['"])?"""
        r"""(?:\s*,\s*['"]([^'"]+)['"])?""",
        re.MULTILINE,
    )
    _GROUP_START = re.compile(r"^\s*group\s+(.+?)\s+do", re.MULTILINE)
    _GROUP_END = re.compile(r"^\s*end\b", re.MULTILINE)
    _DEV_GROUPS = {"development", "test", "doc"}

    def parse(self, content: str, filename: str) -> list[Dependency]:
        deps: list[Dependency] = []
        dev_ranges: list[tuple[int, int]] = []
        for gm in self._GROUP_START.finditer(content):
            groups_raw = gm.group(1).lower()
            group_names = set(re.findall(r":(\w+)", groups_raw))
            if group_names & self._DEV_GROUPS:
                start = gm.end()
                end_match = self._GROUP_END.search(content, start)
                end = end_match.start() if end_match else len(content)
                dev_ranges.append((start, end))

        for m in self._GEM_LINE.finditer(content):
            name = m.group(1)
            v1 = (m.group(2) or "").strip()
            v2 = (m.group(3) or "").strip()
            constraint = f"{v1}, {v2}" if v2 else v1
            if constraint and (constraint.startswith(":") or "=>" in constraint):
                constraint = ""
            pos = m.start()
            is_dev = any(s <= pos <= e for s, e in dev_ranges)
            deps.append(Dependency(
                name=name, version_constraint=constraint,
                source_file=filename, pinning_type=self.classify_pinning(constraint),
                is_dev=is_dev,
            ))
        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps
