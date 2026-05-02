# 📖 User Guide — Repository Dependency Analyzer

This guide walks you through everything you need to know to use the GitHub Repository Dependency Analyzer effectively.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Authentication Setup](#authentication-setup)
5. [Single Repository Analysis](#single-repository-analysis)
6. [Batch Mode](#batch-mode)
7. [Understanding the Output](#understanding-the-output)
8. [Reading the Health Score](#reading-the-health-score)
9. [CLI Reference](#cli-reference)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The Repository Dependency Analyzer is a command-line tool that:

1. Connects to the **GitHub REST API**
2. **Detects** which programming ecosystem(s) a repository uses
3. **Parses** dependency manifest files (requirements.txt, package.json, pom.xml, etc.)
4. **Computes** a health score (0–100) and risk level (LOW / MEDIUM / HIGH)
5. **Generates** a JSON report and a Markdown report

It supports **7 ecosystems**: Python, Node.js, Java, Go, Ruby, Rust, and PHP.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Python | 3.11 or later |
| pip | Comes with Python |
| Internet | Required for GitHub API access |
| GitHub Token | Optional but recommended |

### Checking Your Python Version

```bash
python --version
# Should output: Python 3.11.x or higher
```

---

## Installation

### Step 1: Navigate to the Project Directory

```bash
cd "path/to/Dependency Analyzer ✅"
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs only one external library: `requests`.

### Step 3: Verify Installation

```bash
python -m analyzer --version
# Output: repo-dep-analyzer 1.0.0
```

---

## Authentication Setup

### Why Use a Token?

| Mode | Rate Limit | Per Hour |
|------|-----------|----------|
| Without token | 60 requests | ~3-5 repos |
| With token | 5,000 requests | ~500+ repos |

Each repo analysis uses **3–10 API calls** depending on how many manifest files it has.

### How to Create a GitHub Token

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Give it a name (e.g., "Dependency Analyzer")
4. Select scope: **`public_repo`** (that's all you need)
5. Click **Generate token**
6. Copy the token (it starts with `ghp_`)

### How to Use the Token

**Method 1: Environment Variable (recommended)**

```powershell
# PowerShell
$env:GITHUB_TOKEN="ghp_your_token_here"
```

```bash
# Linux / macOS
export GITHUB_TOKEN=ghp_your_token_here
```

**Method 2: CLI Flag**

```bash
python -m analyzer django/django --token ghp_your_token_here
```

---

## Single Repository Analysis

### Basic Usage

```bash
python -m analyzer owner/repo
```

### Examples

```bash
# Analyze Django (Python)
python -m analyzer django/django

# Analyze Express.js (Node.js)
python -m analyzer expressjs/express

# Analyze Spring Framework (Java)
python -m analyzer spring-projects/spring-framework

# Analyze Gin (Go)
python -m analyzer gin-gonic/gin

# Analyze Rails (Ruby)
python -m analyzer rails/rails

# Analyze Servo (Rust)
python -m analyzer servo/servo

# Analyze Laravel (PHP)
python -m analyzer laravel/laravel
```

### What Happens

1. The tool displays a banner with your API rate limit status
2. It fetches the repo metadata (stars, description, language)
3. It lists the repo root and detects ecosystem files
4. It downloads and parses each manifest file
5. It computes the health score
6. It saves reports to the `reports/` directory

---

## Batch Mode

### Creating a Batch File

Create a text file with one `owner/repo` per line:

```text
# repos.txt
# Comments start with #

django/django
pallets/flask
expressjs/express
gin-gonic/gin
laravel/laravel
```

### Running Batch Analysis

```bash
python -m analyzer --batch repos.txt
```

Or with a short flag:

```bash
python -m analyzer -b repos.txt
```

### Custom Output Directory

```bash
python -m analyzer -b repos.txt -o custom_reports
```

---

## Understanding the Output

### Output Directory Structure

After running the analyzer, you'll find:

```
reports/
├── django_django.json       # Machine-readable JSON
├── django_django.md         # Human-readable Markdown
├── pallets_flask.json
├── pallets_flask.md
└── ...
```

### JSON Report Structure

```json
{
  "repository": "django/django",
  "analyzed_at": "2026-05-02T12:00:00+00:00",
  "repo_info": {
    "name": "django/django",
    "description": "The Web framework for perfectionists...",
    "language": "Python",
    "stargazers_count": 81000,
    "license": "BSD-3-Clause"
  },
  "ecosystems": {
    "python": {
      "manifest_files": ["requirements.txt", "setup.cfg"],
      "has_lock_file": false,
      "indicator_count": 2
    }
  },
  "dependencies": [
    {
      "name": "asgiref",
      "version_constraint": ">=3.7.0",
      "source_file": "setup.cfg",
      "pinning_type": "minimum",
      "is_dev": false
    }
  ],
  "health": {
    "score": 72,
    "risk_level": "MEDIUM",
    "breakdown": { ... },
    "summary_stats": { ... }
  }
}
```

### Markdown Report

The Markdown report includes:
- Repository metadata table
- Health score with visual badge (🟢 🟡 🔴)
- Score breakdown table
- Full dependency list with version constraints and pinning types

---

## Reading the Health Score

### Score Components

| Component | Max Points | What It Measures |
|-----------|-----------|-----------------|
| Version Pinning Quality | 40 | Exact pins (`==1.2.3`) score highest |
| Version Range Tightness | 20 | Tight ranges (`^`, `~=`) beat open ranges (`>=`) |
| Dependency Count Risk | 15 | Fewer deps = lower supply-chain risk |
| Outdated Version Flags | 15 | Flags pre-1.0 / unstable versions |
| Manifest Completeness | 10 | Lock file presence adds confidence |

### Pinning Types Explained

| Type | Example | Meaning |
|------|---------|---------|
| `exact` | `==1.2.3`, `1.2.3` | Locked to a specific version |
| `compatible` | `^1.2.3`, `~=1.2` | Compatible releases only |
| `range` | `>=1.0,<2.0` | Constrained range |
| `minimum` | `>=1.0` | Floor only — risky |
| `unpinned` | `*`, empty | No constraint — highest risk |

### Risk Level Interpretation

| Level | Score | Action Needed |
|-------|-------|--------------|
| 🟢 LOW | 80–100 | Dependencies are well-managed |
| 🟡 MEDIUM | 50–79 | Review unpinned or loosely pinned deps |
| 🔴 HIGH | 0–49 | Urgent: many unpinned/risky dependencies |

---

## CLI Reference

```
usage: repo-dep-analyzer [-h] [--batch FILE] [--token TOKEN]
                          [--output DIR] [--verbose] [--version]
                          [repo]

positional arguments:
  repo                  Repository (format: owner/repo)

options:
  -h, --help            Show this help message
  --batch FILE, -b FILE Text file with one repo per line
  --token TOKEN, -t TOKEN
                        GitHub Personal Access Token
  --output DIR, -o DIR  Output directory (default: reports)
  --verbose, -v         Enable debug logging
  --version             Show version number
```

---

## Troubleshooting

### "Rate limit exceeded"

**Cause:** You've hit GitHub's API rate limit.

**Fix:** Provide a GitHub token:
```bash
python -m analyzer django/django --token ghp_your_token
```

### "Repository not found"

**Cause:** The repo name is incorrect or the repo is private.

**Fix:** Double-check the `owner/repo` format. For private repos, your token needs appropriate access.

### "No supported dependency manifests found"

**Cause:** The repo doesn't have standard dependency files in its root directory.

**Note:** Some repos keep dependencies in subdirectories. The tool currently scans the root only.

### "Network error"

**Cause:** No internet connection or GitHub is down.

**Fix:** Check your connection and try again. The tool retries up to 3 times automatically.

### TOML Parsing Warnings

**Cause:** Python < 3.11 and `tomli` is not installed.

**Fix:**
```bash
pip install tomli
```

---

*For technical details about the architecture, see [TECHNICAL_DOCUMENT.md](TECHNICAL_DOCUMENT.md).*
