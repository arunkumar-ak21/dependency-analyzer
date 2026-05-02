"""
Java Dependency Parser
======================
Parses Java build files:
    - ``pom.xml``       (Maven — XML)
    - ``build.gradle``  (Gradle — Groovy DSL, regex-based)
"""

import re
import logging
import xml.etree.ElementTree as ET

from .base import BaseParser, Dependency

logger = logging.getLogger(__name__)

# Maven POM namespace
_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


class JavaParser(BaseParser):
    ecosystem = "java"

    def parse(self, content: str, filename: str) -> list[Dependency]:
        fname = filename.lower()
        if fname == "pom.xml":
            return self._parse_pom(content, filename)
        elif fname.startswith("build.gradle"):
            return self._parse_gradle(content, filename)
        else:
            logger.warning("Unknown Java manifest: %s", filename)
            return []

    # ------------------------------------------------------------------
    # pom.xml (Maven)
    # ------------------------------------------------------------------
    def _parse_pom(self, content: str, filename: str) -> list[Dependency]:
        """
        Extract ``<dependency>`` blocks from a Maven POM.

        Handles both namespaced and non-namespaced XML.
        Property placeholders (``${foo.version}``) are recorded as-is.
        """
        deps: list[Dependency] = []
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            logger.error("XML parse error in %s: %s", filename, exc)
            return deps

        # Try with namespace first, then without
        dep_elements = root.findall(".//m:dependencies/m:dependency", _NS)
        if not dep_elements:
            dep_elements = root.findall(".//dependencies/dependency")

        for dep_el in dep_elements:
            group = self._find_text(dep_el, "groupId")
            artifact = self._find_text(dep_el, "artifactId")
            version = self._find_text(dep_el, "version")
            scope = self._find_text(dep_el, "scope")

            if not artifact:
                continue

            name = f"{group}:{artifact}" if group else artifact
            constraint = version or ""
            is_dev = scope in ("test", "provided")

            deps.append(Dependency(
                name=name,
                version_constraint=constraint,
                source_file=filename,
                pinning_type=self._classify_maven_version(constraint),
                is_dev=is_dev,
            ))

        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps

    @staticmethod
    def _find_text(element: ET.Element, tag: str) -> str:
        """Find a child element text, trying both namespaced and bare tags."""
        child = element.find(f"m:{tag}", _NS)
        if child is None:
            child = element.find(tag)
        return (child.text or "").strip() if child is not None else ""

    @staticmethod
    def _classify_maven_version(v: str) -> str:
        if not v or v.startswith("${"):
            return "unpinned"
        if "[" in v or "(" in v:
            return "range"
        return "exact"

    # ------------------------------------------------------------------
    # build.gradle (Gradle — Groovy DSL)
    # ------------------------------------------------------------------
    # Matches patterns like:
    #   implementation 'com.google.guava:guava:31.1-jre'
    #   testImplementation "junit:junit:4.13.2"
    #   api group: 'com.fasterxml', name: 'jackson-core', version: '2.15.0'
    _GRADLE_SHORT = re.compile(
        r"""(?:implementation|api|compile|runtime|testImplementation|"""
        r"""testCompile|classpath|annotationProcessor)"""
        r"""\s+['"]([^'"]+):([^'"]+):([^'"]*?)['"]""",
        re.IGNORECASE,
    )
    _GRADLE_MAP = re.compile(
        r"""group:\s*['"]([^'"]+)['"],\s*name:\s*['"]([^'"]+)['"]"""
        r"""(?:,\s*version:\s*['"]([^'"]*?)['"])?""",
        re.IGNORECASE,
    )

    _DEV_CONFIGS = {"testimplementation", "testcompile", "testruntime", "testruntimeonly"}

    def _parse_gradle(self, content: str, filename: str) -> list[Dependency]:
        deps: list[Dependency] = []
        seen = set()

        for m in self._GRADLE_SHORT.finditer(content):
            config = m.group(0).split()[0].lower()
            group, artifact, version = m.group(1), m.group(2), m.group(3)
            key = f"{group}:{artifact}"
            if key in seen:
                continue
            seen.add(key)
            deps.append(Dependency(
                name=key,
                version_constraint=version,
                source_file=filename,
                pinning_type="exact" if version else "unpinned",
                is_dev=(config in self._DEV_CONFIGS),
            ))

        for m in self._GRADLE_MAP.finditer(content):
            group, artifact = m.group(1), m.group(2)
            version = m.group(3) or ""
            key = f"{group}:{artifact}"
            if key in seen:
                continue
            seen.add(key)
            deps.append(Dependency(
                name=key,
                version_constraint=version,
                source_file=filename,
                pinning_type="exact" if version else "unpinned",
            ))

        logger.info("Parsed %d dependencies from %s", len(deps), filename)
        return deps
