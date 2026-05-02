"""
Base Parser
===========
Abstract base class for all ecosystem-specific dependency parsers.

Every concrete parser must implement ``parse(content, filename)`` and
return a list of ``Dependency`` dicts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Dependency:
    """
    Represents a single dependency extracted from a manifest file.

    Attributes
    ----------
    name : str
        Package name (e.g. ``"requests"``).
    version_constraint : str
        Raw version string from the manifest (e.g. ``">=2.28,<3"``).
        Empty string means *unpinned*.
    source_file : str
        The manifest filename this dependency was read from.
    pinning_type : str
        One of ``"exact"``, ``"range"``, ``"minimum"``, ``"compatible"``,
        ``"unpinned"``, or ``"complex"``.
    is_dev : bool
        Whether this is a dev/test dependency.
    """
    name: str
    version_constraint: str = ""
    source_file: str = ""
    pinning_type: str = "unpinned"
    is_dev: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class BaseParser(ABC):
    """
    Interface that every ecosystem parser must implement.
    """

    # Human-readable ecosystem name (set by subclasses)
    ecosystem: str = ""

    @abstractmethod
    def parse(self, content: str, filename: str) -> list[Dependency]:
        """
        Parse the text content of a dependency manifest file.

        Parameters
        ----------
        content : str
            Full text content of the file.
        filename : str
            Original filename (e.g. ``"requirements.txt"``).

        Returns
        -------
        list[Dependency]
        """

    # ------------------------------------------------------------------
    # Shared helpers for version-constraint classification
    # ------------------------------------------------------------------
    @staticmethod
    def classify_pinning(constraint: str) -> str:
        """
        Classify a version constraint string into a pinning category.

        Categories
        ----------
        exact       : ``==1.2.3``, ``=1.2.3``, ``1.2.3`` (bare semver)
        range       : ``>=1.0,<2.0``
        minimum     : ``>=1.0``, ``>1.0``
        compatible  : ``~=1.4``, ``^1.4``, ``~1.4``
        unpinned    : ``*``, empty, ``latest``
        complex     : anything else
        """
        c = constraint.strip()
        if not c or c == "*" or c.lower() == "latest":
            return "unpinned"
        if c.startswith("==") or c.startswith("= "):
            return "exact"
        if c.startswith("~=") or c.startswith("~>") or c.startswith("^") or c.startswith("~"):
            return "compatible"
        # Bare semver like "1.2.3" (no operator)
        if c[0].isdigit() and "," not in c and ">" not in c and "<" not in c:
            return "exact"
        # Range: contains both > and < operators, or comma-separated
        if "," in c or (">=" in c and "<" in c) or (">" in c and "<" in c):
            return "range"
        if c.startswith(">=") or c.startswith(">"):
            return "minimum"
        if c.startswith("<=") or c.startswith("<") or c.startswith("!="):
            return "complex"
        return "complex"
