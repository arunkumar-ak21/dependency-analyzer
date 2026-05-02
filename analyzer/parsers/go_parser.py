"""
Go Dependency Parser
====================
Parses ``go.mod`` to extract module requirements.
"""

import re
import logging

from .base import BaseParser, Dependency

logger = logging.getLogger(__name__)


class GoParser(BaseParser):
    ecosystem = "go"

    # Single-line require:  require golang.org/x/text v0.3.7
    _SINGLE = re.compile(r"^\s*require\s+(\S+)\s+(v[\d.]+\S*)", re.MULTILINE)

    # Block require:
    #   require (
    #       golang.org/x/text v0.3.7
    #   )
    _BLOCK = re.compile(r"require\s*\((.*?)\)", re.DOTALL)
    _BLOCK_LINE = re.compile(r"^\s*(\S+)\s+(v[\d.]+\S*)", re.MULTILINE)

    # Indirect marker
    _INDIRECT = re.compile(r"//\s*indirect", re.IGNORECASE)

    def parse(self, content: str, filename: str) -> list[Dependency]:
        deps: list[Dependency] = []
        seen: set[str] = set()

        # Parse require blocks
        for block_match in self._BLOCK.finditer(content):
            block = block_match.group(1)
            for m in self._BLOCK_LINE.finditer(block):
                module, version = m.group(1), m.group(2)
                if module in seen:
                    continue
                seen.add(module)
                # Check if the line contains "// indirect"
                line_start = block.rfind("\n", 0, m.start()) + 1
                line_end = block.find("\n", m.end())
                line_text = block[line_start:line_end if line_end != -1 else len(block)]
                is_dev = bool(self._INDIRECT.search(line_text))
                deps.append(Dependency(
                    name=module,
                    version_constraint=version,
                    source_file=filename,
                    pinning_type="exact",
                    is_dev=is_dev,
                ))

        # Parse single-line requires (outside blocks)
        for m in self._SINGLE.finditer(content):
            module, version = m.group(1), m.group(2)
            if module in seen:
                continue
            seen.add(module)
            deps.append(Dependency(
                name=module,
                version_constraint=version,
                source_file=filename,
                pinning_type="exact",
            ))

        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps
