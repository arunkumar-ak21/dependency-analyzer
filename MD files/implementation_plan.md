# Implementation Plan — GitHub Repository Dependency Analyzer

## Architecture

```
repo_dependency_analyzer/
├── analyzer/                    # Core package
│   ├── __init__.py
│   ├── cli.py                   # CLI entry point (argparse)
│   ├── github_client.py         # GitHub REST API client with rate-limit handling
│   ├── detector.py              # Language/ecosystem auto-detection
│   ├── parsers/                 # Per-ecosystem dependency parsers
│   │   ├── __init__.py
│   │   ├── base.py              # Abstract parser interface
│   │   ├── python_parser.py     # requirements.txt, setup.py, Pipfile, pyproject.toml
│   │   ├── node_parser.py       # package.json, package-lock.json
│   │   ├── java_parser.py       # pom.xml, build.gradle
│   │   ├── go_parser.py         # go.mod
│   │   ├── ruby_parser.py       # Gemfile
│   │   ├── rust_parser.py       # Cargo.toml
│   │   └── php_parser.py        # composer.json
│   ├── scorer.py                # Health scoring engine
│   └── reporter.py              # JSON + Markdown report generation
├── reports/                     # Output directory (auto-created)
├── repos.txt                    # Sample batch file
├── requirements.txt             # Minimal deps (requests only)
├── README.md                    # Setup & usage
├── USER_GUIDE.md                # End-user guide
└── TECHNICAL_DOCUMENT.md        # Architecture & engineering decisions
```

## Modules

| Module | Responsibility |
|---|---|
| `cli.py` | Parse CLI args, orchestrate analysis, handle batch mode |
| `github_client.py` | Authenticated & unauthenticated GitHub API calls, rate-limit backoff |
| `detector.py` | Map filenames → ecosystem, rank by confidence |
| `parsers/*.py` | Extract dependency name + version constraint from manifest files |
| `scorer.py` | Compute health score (0–100) and risk level (LOW/MEDIUM/HIGH) |
| `reporter.py` | Generate structured JSON and human-readable Markdown reports |

## Health Scoring Algorithm

| Criterion | Weight | Details |
|---|---|---|
| Version pinning quality | 40 | Exact pins (==, =) score highest; unpinned scores 0 |
| Version range tightness | 20 | Tight ranges (~=, ^) score higher than wide (>=, *) |
| Dependency count risk | 15 | Fewer deps = healthier; >100 penalized |
| Outdated dependency signals | 15 | Pre-1.0 versions, 0.x ranges flagged |
| Manifest completeness | 10 | Lock files present = bonus |

Risk Levels: 80–100 = LOW, 50–79 = MEDIUM, 0–49 = HIGH

## Key Design Decisions
- **Single external dependency**: `requests` only
- **TOML parsing**: Use `tomllib` (Python 3.11+) with `tomli` fallback
- **XML parsing**: `xml.etree.ElementTree` (stdlib)
- **Rate limiting**: Exponential backoff with `X-RateLimit-Remaining` header inspection
- **Auth**: `GITHUB_TOKEN` env var or `--token` CLI flag
