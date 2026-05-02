# 📦 GitHub Repository Dependency Analyzer

A production-grade CLI tool that connects to the GitHub API, automatically detects programming ecosystems, parses dependency manifests, computes health scores, and generates comprehensive reports.

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![License MIT](https://img.shields.io/badge/license-MIT-green.svg)

---

## ✨ Features

- **Multi-Ecosystem Support** — Python, Node.js, Java, Go, Ruby, Rust, PHP
- **Automatic Detection** — identifies ecosystems from repo root file structure
- **Health Scoring** — weighted 0–100 score with LOW / MEDIUM / HIGH risk levels
- **Dual Reports** — structured JSON + human-readable Markdown per repo
- **Batch Mode** — analyze multiple repos from a text file in one command
- **Rate-Limit Aware** — automatic backoff with GitHub API rate limits
- **Minimal Dependencies** — only `requests` as external dependency

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or later
- A GitHub Personal Access Token (recommended, not required)

### Installation

```bash
# Clone or download the project
cd "Dependency Analyzer ✅"

# Install the single dependency
pip install -r requirements.txt
```

### Set Up Authentication (Recommended)

Without a token you are limited to **60 API requests/hour**. With a token: **5,000/hour**.

```bash
# Option A: Environment variable
export GITHUB_TOKEN=ghp_your_token_here      # Linux/macOS
set GITHUB_TOKEN=ghp_your_token_here         # Windows CMD
$env:GITHUB_TOKEN="ghp_your_token_here"      # PowerShell

# Option B: Pass directly via CLI flag
python -m analyzer django/django --token ghp_your_token_here
```

### Analyze a Single Repository

```bash
python -m analyzer django/django
```

### Batch Mode — Analyze Multiple Repos

```bash
python -m analyzer --batch repos.txt
```

### Custom Output Directory

```bash
python -m analyzer django/django -o my_reports
```

### Verbose / Debug Mode

```bash
python -m analyzer django/django -v
```

---

## 📁 Output

Reports are saved to the `reports/` directory (or your custom path):

| File | Format | Description |
|------|--------|-------------|
| `django_django.json` | JSON | Machine-readable structured data |
| `django_django.md` | Markdown | Human-readable report with tables |

---

## 📖 Supported Ecosystems & Manifest Files

| Ecosystem | Manifest Files |
|-----------|---------------|
| Python | `requirements.txt`, `setup.py`, `setup.cfg`, `Pipfile`, `pyproject.toml` |
| Node.js | `package.json` |
| Java | `pom.xml`, `build.gradle`, `build.gradle.kts` |
| Go | `go.mod` |
| Ruby | `Gemfile` |
| Rust | `Cargo.toml` |
| PHP | `composer.json` |

---

## 🏥 Health Scoring

The tool computes a **health score from 0 to 100** based on:

| Criterion | Weight | What It Measures |
|-----------|--------|-----------------|
| Version Pinning Quality | 40% | How precisely versions are locked |
| Version Range Tightness | 20% | Preference for exact/compatible over wide ranges |
| Dependency Count Risk | 15% | Fewer direct deps = lower supply-chain risk |
| Outdated Version Flags | 15% | Pre-1.0 / unstable version patterns |
| Manifest Completeness | 10% | Presence of lock files |

### Risk Levels

| Score Range | Risk Level | Meaning |
|-------------|------------|---------|
| 80 – 100 | 🟢 LOW | Well-managed dependencies |
| 50 – 79 | 🟡 MEDIUM | Some areas need attention |
| 0 – 49 | 🔴 HIGH | Significant dependency risks |

---

## 📂 Project Structure

```
Dependency Analyzer ✅/
├── analyzer/                  # Core Python package
│   ├── __init__.py            # Package metadata
│   ├── __main__.py            # python -m entry point
│   ├── cli.py                 # CLI argument parsing & orchestration
│   ├── github_client.py       # GitHub REST API client
│   ├── detector.py            # Ecosystem auto-detection
│   ├── scorer.py              # Health scoring engine
│   ├── reporter.py            # JSON & Markdown report generation
│   └── parsers/               # Per-ecosystem parsers
│       ├── __init__.py
│       ├── base.py            # Abstract parser + Dependency dataclass
│       ├── python_parser.py
│       ├── node_parser.py
│       ├── java_parser.py
│       ├── go_parser.py
│       ├── ruby_parser.py
│       ├── rust_parser.py
│       └── php_parser.py
├── reports/                   # Generated reports (auto-created)
├── repos.txt                  # Sample batch file
├── requirements.txt           # Python dependencies
├── README.md                  # This file
├── USER_GUIDE.md              # End-user guide
└── TECHNICAL_DOCUMENT.md      # Architecture & design decisions
```

---

## 📝 Additional Documentation

- **[User Guide](USER_GUIDE.md)** — step-by-step usage instructions
- **[Technical Document](TECHNICAL_DOCUMENT.md)** — architecture, design decisions, engineering rationale

---

## ⚖️ License

This project is provided for educational and internship purposes.

---

*Built by Arun Kumar — Internship Project 2026*
