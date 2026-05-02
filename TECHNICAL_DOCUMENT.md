# 🏗️ Technical Document — Repository Dependency Analyzer

## Architecture & Engineering Decisions

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Module Design](#module-design)
4. [Data Flow](#data-flow)
5. [Ecosystem Detection Strategy](#ecosystem-detection-strategy)
6. [Parser Design](#parser-design)
7. [Health Scoring Algorithm](#health-scoring-algorithm)
8. [GitHub API Integration](#github-api-integration)
9. [Error Handling Strategy](#error-handling-strategy)
10. [Design Decisions & Trade-offs](#design-decisions--trade-offs)
11. [Extensibility](#extensibility)
12. [Limitations & Future Work](#limitations--future-work)

---

## System Overview

The Repository Dependency Analyzer is a Python CLI tool that performs static analysis of dependency manifests in GitHub repositories. It operates entirely via the GitHub REST API (no cloning required) and produces structured health reports.

### Key Design Goals

| Goal | Approach |
|------|----------|
| Minimal dependencies | Only `requests` as external dep |
| Multi-ecosystem | 7 ecosystems via pluggable parser architecture |
| Production-ready | Retry logic, rate-limit handling, graceful errors |
| Batch capable | Text-file input for bulk analysis |
| Dual output | Machine-readable JSON + human-readable Markdown |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    CLI Layer                     │
│              (cli.py + __main__.py)              │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │  GitHub   │  │Ecosystem │  │   Parser     │  │
│  │  Client   │→ │ Detector │→ │  Registry    │  │
│  │          │  │          │  │  (7 parsers) │  │
│  └──────────┘  └──────────┘  └──────┬───────┘  │
│                                      │          │
│                              ┌───────▼───────┐  │
│                              │    Health     │  │
│                              │    Scorer     │  │
│                              └───────┬───────┘  │
│                                      │          │
│                              ┌───────▼───────┐  │
│                              │    Report     │  │
│                              │   Generator   │  │
│                              └───────────────┘  │
└─────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | File | Role |
|-----------|------|------|
| CLI | `cli.py` | Arg parsing, orchestration, console output |
| GitHub Client | `github_client.py` | HTTP requests, auth, rate-limit, retry |
| Detector | `detector.py` | Maps filenames → ecosystems |
| Parsers | `parsers/*.py` | Extract deps from manifest file content |
| Scorer | `scorer.py` | Multi-criteria weighted scoring |
| Reporter | `reporter.py` | JSON + Markdown file generation |

---

## Module Design

### 1. GitHub Client (`github_client.py`)

**Pattern:** Wrapper class around `requests.Session`.

**Key decisions:**
- Uses a persistent `Session` for connection pooling and header reuse
- Rate-limit handling reads `X-RateLimit-Reset` header and computes exact sleep time
- Exponential backoff for transient 5xx errors (factor=2, max 3 retries)
- File content fetched via Contents API (base64-decoded), with raw URL fallback for large files
- 404s are returned as `None` — never raised as exceptions (caller decides)

### 2. Ecosystem Detector (`detector.py`)

**Pattern:** Lookup table with indicator scoring.

**Key decisions:**
- A flat dictionary maps lowercase filenames to `(ecosystem, is_manifest)` tuples
- Both manifest files and lock files are indicators, but only manifests are parsed
- When multiple ecosystems are detected, they're ranked by indicator count
- Detection is root-only (no recursive directory scanning) to minimize API calls

### 3. Parser System (`parsers/`)

**Pattern:** Strategy pattern with a registry.

- `BaseParser` is an abstract class defining the `parse(content, filename)` contract
- `Dependency` is a dataclass representing a single parsed dependency
- `PARSER_REGISTRY` is a `dict[str, type]` mapping ecosystem names to parser classes
- Each parser handles 1–5 file formats for its ecosystem

### 4. Health Scorer (`scorer.py`)

**Pattern:** Weighted multi-criteria scoring.

- Five criteria with fixed weights summing to 100
- Each sub-scorer returns its weighted contribution
- Risk levels derived from final score via fixed thresholds

### 5. Report Generator (`reporter.py`)

**Pattern:** Template-based rendering.

- JSON uses `json.dump` with pretty-printing
- Markdown is rendered via string concatenation (no template engine dependency)
- Output directory is auto-created

---

## Data Flow

```
User Input (repo name)
    │
    ▼
GitHub Client → fetch repo info (metadata)
    │
    ▼
GitHub Client → list root directory (file names)
    │
    ▼
Ecosystem Detector → match filenames → identified ecosystems
    │
    ▼
For each ecosystem:
    GitHub Client → fetch manifest file content
        │
        ▼
    Parser → extract [Dependency, Dependency, ...]
    │
    ▼
Health Scorer → compute score + risk level
    │
    ▼
Report Generator → write JSON + Markdown files
```

---

## Ecosystem Detection Strategy

The detector uses a **filename-based approach** rather than relying on GitHub's `language` field. This is more reliable because:

1. GitHub's language detection is based on file extensions (bytes of code), which can be misleading for polyglot repos
2. A repo can have dependencies in multiple ecosystems (e.g., a Python backend + Node.js frontend)
3. The presence of a manifest file is definitive proof that the ecosystem is in use

### Indicator File Weights

Each file contributes +1 to its ecosystem's indicator count. Ecosystems with more indicators are ranked higher. This naturally handles polyglot repos.

---

## Parser Design

### Common Interface

All parsers extend `BaseParser` and implement:

```python
def parse(self, content: str, filename: str) -> list[Dependency]
```

### Per-Ecosystem Strategies

| Ecosystem | Strategy | Libraries Used |
|-----------|----------|---------------|
| Python | Regex (requirements.txt), TOML (pyproject.toml), line parsing (setup.cfg, Pipfile) | `tomllib` (stdlib 3.11+) |
| Node.js | JSON parsing | `json` (stdlib) |
| Java | XML parsing (pom.xml), Regex (build.gradle) | `xml.etree.ElementTree` (stdlib) |
| Go | Regex on `go.mod` syntax | — |
| Ruby | Regex on Gemfile DSL | — |
| Rust | TOML parsing | `tomllib` (stdlib 3.11+) |
| PHP | JSON parsing | `json` (stdlib) |

### Version Constraint Classification

Every parser classifies each dependency's version constraint into one of:

| Type | Score | Example |
|------|-------|---------|
| `exact` | 1.0 | `==1.2.3`, `1.2.3` |
| `compatible` | 0.8 | `^1.2.3`, `~=1.2` |
| `range` | 0.6 | `>=1.0,<2.0` |
| `minimum` | 0.3 | `>=1.0` |
| `complex` | 0.4 | `!=1.0`, `<2 \|\| >3` |
| `unpinned` | 0.0 | `*`, empty, `latest` |

This classification drives the health score.

---

## Health Scoring Algorithm

### Formula

```
Total Score = Pinning Quality (40) + Range Tightness (20) +
              Count Risk (15) + Outdated Flags (15) +
              Completeness (10)
```

### Criterion 1: Version Pinning Quality (40 points)

```
score = (Σ pinning_score[d] for d in deps) / len(deps) × 40
```

Where `pinning_score` maps each dependency's type to [0.0, 1.0].

### Criterion 2: Range Tightness (20 points)

```
score = (count of {exact, compatible} deps) / total × 20
```

Rewards tight version specifications over loose ones.

### Criterion 3: Dependency Count Risk (15 points)

| Dep Count | Score |
|-----------|-------|
| ≤ 10 | 15.0 (full) |
| 11–30 | 13.5 |
| 31–60 | 10.5 |
| 61–100 | 7.5 |
| > 100 | 4.5 |

### Criterion 4: Outdated Version Flags (15 points)

Flags dependencies with `0.x` versions (pre-stable). Penalizes proportionally:
```
score = 15 × (1 − flagged_ratio × 0.6)
```

### Criterion 5: Manifest Completeness (10 points)

- Base: 5 points (manifest exists)
- Lock file present: +5 points

### Risk Level Mapping

| Score | Level |
|-------|-------|
| 80–100 | 🟢 LOW |
| 50–79 | 🟡 MEDIUM |
| 0–49 | 🔴 HIGH |

---

## GitHub API Integration

### Endpoints Used

| Endpoint | Purpose | Calls/Repo |
|----------|---------|-----------|
| `GET /repos/{owner}/{repo}` | Repo metadata | 1 |
| `GET /repos/{owner}/{repo}/contents/` | List root files | 1 |
| `GET /repos/{owner}/{repo}/contents/{path}` | Fetch file content | 1 per manifest |
| `GET /rate_limit` | Check quota | 1 (at start) |

**Total API calls per repo: 3–10** (depending on manifest count).

### Rate Limiting

1. Before each batch, the tool checks `/rate_limit` and displays remaining quota
2. On HTTP 403 with "rate limit" in the body:
   - Read `X-RateLimit-Reset` header
   - If wait < 5 minutes: sleep and retry
   - If wait > 5 minutes: raise `RateLimitError` and stop
3. On HTTP 5xx: exponential backoff (2s, 4s, 8s)

### Authentication

- Token passed via `Authorization: token {PAT}` header
- Supports `GITHUB_TOKEN` env var or `--token` CLI flag
- Without token: 60 req/hr; with token: 5,000 req/hr

---

## Error Handling Strategy

| Error Type | Handling |
|-----------|----------|
| Network timeout | Retry up to 3 times with backoff |
| HTTP 404 | Return `None`, log warning |
| HTTP 403 (rate limit) | Sleep until reset or abort |
| HTTP 5xx | Retry with exponential backoff |
| JSON/XML parse error | Log error, skip file, continue |
| Invalid repo format | Fail fast with clear message |
| Missing batch file | Fail fast with error |
| Unknown ecosystem | Skip silently, log warning |

The tool never crashes on a single repo failure in batch mode — it logs the error and continues.

---

## Design Decisions & Trade-offs

### 1. No Repository Cloning

**Decision:** Use the GitHub Contents API instead of `git clone`.

**Rationale:**
- Much faster (3–10 HTTP requests vs. cloning entire history)
- No disk space requirements
- No git dependency
- Sufficient for manifest-file analysis

**Trade-off:** Cannot scan files in subdirectories (e.g., `backend/requirements.txt`).

### 2. Single External Dependency

**Decision:** Only `requests` as a third-party package.

**Rationale:**
- Simplifies installation and reduces supply-chain risk
- TOML parsing uses `tomllib` (stdlib in 3.11+)
- XML parsing uses `xml.etree.ElementTree` (stdlib)
- JSON parsing uses `json` (stdlib)

### 3. Regex-Based Parsing for Some Ecosystems

**Decision:** Use regex instead of full language parsers for Gemfile, build.gradle, setup.py.

**Rationale:**
- Avoids heavy dependencies (e.g., Ruby parser, Groovy parser)
- Handles 90%+ of real-world file patterns
- Acceptable trade-off: may miss edge cases in unusual file structures

### 4. Root-Only Scanning

**Decision:** Only scan the repository root directory.

**Rationale:**
- Minimizes API calls (1 call for listing vs. recursive tree traversal)
- Most well-structured repos have manifests in the root
- Keeps the tool fast and within rate limits

### 5. No Vulnerability Database Integration

**Decision:** Health score is based on version pinning patterns, not known CVEs.

**Rationale:**
- CVE databases require external service integration (OSV, NVD)
- Would add significant complexity and API dependencies
- Pinning quality is a strong proxy for dependency hygiene

---

## Extensibility

### Adding a New Ecosystem

1. Create `analyzer/parsers/new_ecosystem_parser.py`
2. Implement `class NewParser(BaseParser)`
3. Register in `analyzer/parsers/__init__.py`:
   ```python
   PARSER_REGISTRY["new_ecosystem"] = NewParser
   ```
4. Add indicator files in `analyzer/detector.py`:
   ```python
   "manifest.ext": ("new_ecosystem", True),
   ```

### Modifying Health Scoring

All weights and thresholds are constants in `scorer.py`. Adjust:
- `W_PINNING`, `W_TIGHTNESS`, etc. (must sum to 100)
- `PINNING_SCORES` dict for per-type weights
- `compute_risk_level()` for threshold changes

---

## Limitations & Future Work

### Current Limitations

1. **Root-only scanning** — misses manifests in subdirectories
2. **No transitive dependency analysis** — only direct dependencies
3. **No CVE/vulnerability checking** — scoring is based on patterns only
4. **Gradle Kotlin DSL** — limited support (basic regex)
5. **Monorepo support** — does not scan workspace/subproject manifests

### Future Enhancements

1. **Recursive scanning** — optional `--deep` flag to scan subdirectories
2. **Vulnerability integration** — query OSV.dev or GitHub Advisory Database
3. **Version freshness** — compare against latest versions on registries
4. **Historical trending** — track health scores over time
5. **GitHub Actions integration** — run as a CI check
6. **HTML report output** — interactive web-based reports

---

*Document authored by Arun Kumar — May 2026*
