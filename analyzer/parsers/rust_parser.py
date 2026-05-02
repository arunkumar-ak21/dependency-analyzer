"""
Rust Dependency Parser
======================
Parses ``Cargo.toml`` to extract crate dependencies.
"""

import logging
from typing import Optional
from .base import BaseParser, Dependency

logger = logging.getLogger(__name__)


class RustParser(BaseParser):
    ecosystem = "rust"

    def parse(self, content: str, filename: str) -> list[Dependency]:
        data = self._load_toml(content)
        if data is None:
            return self._parse_regex(content, filename)

        deps: list[Dependency] = []
        for section, is_dev in [("dependencies", False), ("dev-dependencies", True),
                                ("build-dependencies", False)]:
            dep_map = data.get(section, {})
            for name, spec in dep_map.items():
                if isinstance(spec, str):
                    constraint = spec
                elif isinstance(spec, dict):
                    constraint = spec.get("version", "")
                else:
                    constraint = ""
                deps.append(Dependency(
                    name=name, version_constraint=constraint,
                    source_file=filename,
                    pinning_type=self.classify_pinning(constraint),
                    is_dev=is_dev,
                ))
        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps

    @staticmethod
    def _load_toml(text: str) -> Optional[dict]:
        try:
            import tomllib
            return tomllib.loads(text)
        except ImportError:
            pass
        try:
            import tomli
            return tomli.loads(text)
        except ImportError:
            pass
        return None

    def _parse_regex(self, content: str, filename: str) -> list[Dependency]:
        """Regex fallback when no TOML parser is available."""
        import re
        deps: list[Dependency] = []
        section = None
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                section = stripped.strip("[]").strip().lower()
                continue
            if section and "dependencies" in section and "=" in stripped:
                key, _, val = stripped.partition("=")
                name = key.strip()
                val = val.strip().strip('"').strip("'")
                if val.startswith("{"):
                    vm = re.search(r'version\s*=\s*"([^"]*)"', val)
                    constraint = vm.group(1) if vm else ""
                else:
                    constraint = val
                is_dev = "dev" in section
                deps.append(Dependency(
                    name=name, version_constraint=constraint,
                    source_file=filename,
                    pinning_type=self.classify_pinning(constraint),
                    is_dev=is_dev,
                ))
        logger.info("Parsed %d dependencies from %s (regex)", len(deps), filename)
        return deps
