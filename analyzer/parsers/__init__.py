"""
Dependency Parsers
==================
Each parser is responsible for extracting dependency names and version
constraints from a specific ecosystem's manifest files.

Supported ecosystems:
    - Python   (requirements.txt, setup.py, setup.cfg, Pipfile, pyproject.toml)
    - Node.js  (package.json)
    - Java     (pom.xml, build.gradle)
    - Go       (go.mod)
    - Ruby     (Gemfile)
    - Rust     (Cargo.toml)
    - PHP      (composer.json)
"""

from .python_parser import PythonParser
from .node_parser import NodeParser
from .java_parser import JavaParser
from .go_parser import GoParser
from .ruby_parser import RubyParser
from .rust_parser import RustParser
from .php_parser import PhpParser

# Registry mapping ecosystem names to their parser classes.
PARSER_REGISTRY: dict[str, type] = {
    "python": PythonParser,
    "node": NodeParser,
    "java": JavaParser,
    "go": GoParser,
    "ruby": RubyParser,
    "rust": RustParser,
    "php": PhpParser,
}

__all__ = [
    "PythonParser",
    "NodeParser",
    "JavaParser",
    "GoParser",
    "RubyParser",
    "RustParser",
    "PhpParser",
    "PARSER_REGISTRY",
]
