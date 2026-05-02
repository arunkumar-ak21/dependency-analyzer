"""
Python Dependency Parser
========================
Parses Python dependency manifest files:
    - requirements.txt  (PEP 508 style)
    - setup.py          (install_requires extraction via regex)
    - setup.cfg         (INI-style [options] install_requires)
    - Pipfile           (TOML)
    - pyproject.toml    (PEP 621 + Poetry)
"""

import re
import logging
from typing import Optional

from .base import BaseParser, Dependency

logger = logging.getLogger(__name__)


class PythonParser(BaseParser):
    ecosystem = "python"

    def parse(self, content: str, filename: str) -> list[Dependency]:
        """Route to the appropriate sub-parser based on filename."""
        fname = filename.lower()
        if fname == "requirements.txt":
            return self._parse_requirements_txt(content, filename)
        elif fname == "setup.py":
            return self._parse_setup_py(content, filename)
        elif fname == "setup.cfg":
            return self._parse_setup_cfg(content, filename)
        elif fname == "pipfile":
            return self._parse_pipfile(content, filename)
        elif fname == "pyproject.toml":
            return self._parse_pyproject_toml(content, filename)
        else:
            logger.warning("Unknown Python manifest: %s", filename)
            return []

    # ------------------------------------------------------------------
    # requirements.txt
    # ------------------------------------------------------------------
    # Matches lines like:  requests>=2.28.0  or  Django==4.2  or  flask
    _REQ_LINE = re.compile(
        r"^(?P<name>[A-Za-z0-9_][A-Za-z0-9._-]*)"
        r"(?:\[.*?\])?"                        # optional extras [security]
        r"\s*(?P<constraint>[><=!~^][^\s;#]*)?",  # optional version spec
    )

    def _parse_requirements_txt(self, content: str, filename: str) -> list[Dependency]:
        deps: list[Dependency] = []
        for raw_line in content.splitlines():
            line = raw_line.strip()
            # Skip blanks, comments, options, and URLs
            if not line or line.startswith("#") or line.startswith("-") or "://" in line:
                continue
            m = self._REQ_LINE.match(line)
            if m:
                name = m.group("name")
                constraint = (m.group("constraint") or "").strip()
                deps.append(Dependency(
                    name=name,
                    version_constraint=constraint,
                    source_file=filename,
                    pinning_type=self.classify_pinning(constraint),
                ))
        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps

    # ------------------------------------------------------------------
    # setup.py
    # ------------------------------------------------------------------
    _INSTALL_REQUIRES = re.compile(
        r"install_requires\s*=\s*\[([^\]]*)\]", re.DOTALL
    )

    def _parse_setup_py(self, content: str, filename: str) -> list[Dependency]:
        deps: list[Dependency] = []
        match = self._INSTALL_REQUIRES.search(content)
        if not match:
            return deps
        block = match.group(1)
        for item in re.findall(r"""['"]([^'"]+)['"]""", block):
            parsed = self._parse_pep508(item, filename)
            if parsed:
                deps.append(parsed)
        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps

    # ------------------------------------------------------------------
    # setup.cfg
    # ------------------------------------------------------------------
    def _parse_setup_cfg(self, content: str, filename: str) -> list[Dependency]:
        deps: list[Dependency] = []
        in_install_requires = False
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if line.lower().startswith("install_requires"):
                in_install_requires = True
                # Value may start on same line after '='
                _, _, rest = line.partition("=")
                rest = rest.strip()
                if rest:
                    parsed = self._parse_pep508(rest, filename)
                    if parsed:
                        deps.append(parsed)
                continue
            if in_install_requires:
                # Continuation lines are indented
                if not raw_line or (raw_line[0] not in (" ", "\t") and "=" in line):
                    in_install_requires = False
                    continue
                if line and not line.startswith("#"):
                    parsed = self._parse_pep508(line, filename)
                    if parsed:
                        deps.append(parsed)
        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps

    # ------------------------------------------------------------------
    # Pipfile (TOML-like — lightweight parser)
    # ------------------------------------------------------------------
    def _parse_pipfile(self, content: str, filename: str) -> list[Dependency]:
        deps: list[Dependency] = []
        section = None
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if line.startswith("["):
                section = line.strip("[]").strip().lower()
                continue
            if section not in ("packages", "dev-packages"):
                continue
            if "=" not in line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            name = key.strip().strip('"').strip("'")
            val = val.strip().strip('"').strip("'")
            constraint = "" if val == "*" else val
            deps.append(Dependency(
                name=name,
                version_constraint=constraint,
                source_file=filename,
                pinning_type=self.classify_pinning(constraint),
                is_dev=(section == "dev-packages"),
            ))
        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps

    # ------------------------------------------------------------------
    # pyproject.toml (PEP 621 + Poetry)
    # ------------------------------------------------------------------
    def _parse_pyproject_toml(self, content: str, filename: str) -> list[Dependency]:
        """Parse pyproject.toml using tomllib (3.11+) or tomli fallback."""
        data = self._load_toml(content)
        if data is None:
            # Fallback: regex extraction
            return self._parse_pyproject_regex(content, filename)

        deps: list[Dependency] = []

        # PEP 621: [project] dependencies = [...]
        for item in data.get("project", {}).get("dependencies", []):
            parsed = self._parse_pep508(item, filename)
            if parsed:
                deps.append(parsed)

        # PEP 621: optional-dependencies
        for group, items in data.get("project", {}).get("optional-dependencies", {}).items():
            for item in items:
                parsed = self._parse_pep508(item, filename, is_dev=True)
                if parsed:
                    deps.append(parsed)

        # Poetry: [tool.poetry.dependencies]
        poetry = data.get("tool", {}).get("poetry", {})
        for section_key, is_dev in [("dependencies", False), ("dev-dependencies", True)]:
            for name, spec in poetry.get(section_key, {}).items():
                if name.lower() == "python":
                    continue
                if isinstance(spec, str):
                    constraint = "" if spec == "*" else spec
                elif isinstance(spec, dict):
                    constraint = spec.get("version", "")
                else:
                    constraint = ""
                deps.append(Dependency(
                    name=name,
                    version_constraint=constraint,
                    source_file=filename,
                    pinning_type=self.classify_pinning(constraint),
                    is_dev=is_dev,
                ))

        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _load_toml(text: str) -> Optional[dict]:
        """Try to parse TOML text, return None on failure."""
        try:
            import tomllib  # Python ≥ 3.11
            return tomllib.loads(text)
        except ImportError:
            pass
        try:
            import tomli  # pip install tomli (for 3.10 and below)
            return tomli.loads(text)
        except ImportError:
            pass
        return None

    _PEP508 = re.compile(
        r"^(?P<name>[A-Za-z0-9_][A-Za-z0-9._-]*)"
        r"(?:\[.*?\])?"
        r"\s*(?P<constraint>[><=!~^][^\s;]*)?",
    )

    def _parse_pep508(self, spec: str, filename: str, is_dev: bool = False) -> Optional[Dependency]:
        spec = spec.strip()
        m = self._PEP508.match(spec)
        if not m:
            return None
        name = m.group("name")
        constraint = (m.group("constraint") or "").strip()
        return Dependency(
            name=name,
            version_constraint=constraint,
            source_file=filename,
            pinning_type=self.classify_pinning(constraint),
            is_dev=is_dev,
        )

    def _parse_pyproject_regex(self, content: str, filename: str) -> list[Dependency]:
        """Last-resort regex fallback for pyproject.toml when TOML parser is unavailable."""
        deps: list[Dependency] = []
        for m in re.finditer(r"""['"]([A-Za-z0-9_][A-Za-z0-9._-]*(?:\[.*?\])?\s*[><=!~^][^\s'"]*?)['"]""", content):
            parsed = self._parse_pep508(m.group(1), filename)
            if parsed:
                deps.append(parsed)
        return deps
