# Skill Lab

[![PyPI version](https://badge.fury.io/py/skill-lab.svg?v=0.5.0)](https://badge.fury.io/py/skill-lab)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Agent Skills Evaluation Framework**

Your agent's skills are probably broken in at least one way — and you don't know it yet. **Skill Lab** catches skills that drain tokens, never fire, or leak data before they cause damage.

```bash
pip install skill-lab
```

---

## Why Skill Lab

**Performance** — A badly-written skill can triple your token usage with zero gain. We score every skill 0–100 and show exactly what it costs. `sklab evaluate ./my-skill`

**Security** — A malicious skill can exfiltrate company data to an external endpoint. Static checks catch that before the conversation starts. `sklab scan ./my-skill`

**Trigger Testing** — If your description doesn't have enough trigger examples, the skill sits there doing nothing. We generate and run ~13 tests automatically. `sklab trigger ./my-skill`

---

## Quick Start

```bash
# Install
pip install skill-lab

# First run — scans your repo and shows the getting started guide
sklab
```

---

## Commands

| Command / Flag | Description |
|---|---|
| **Evaluate** | |
| `sklab evaluate ./my-skill` | Full quality evaluation — runs all checks, produces a 0–100 score |
| `--verbose / -V` | Show all checks, not just failures |
| `--spec-only / -s` | Only run spec-required checks |
| `--format / -f json` | Output as JSON |
| `--output / -o <file>` | Write output to a file |
| `--all` | Evaluate every skill in the current directory |
| `--repo` | Evaluate every skill from the git repo root |
| **Check** | |
| `sklab check ./my-skill` | Quick pass/fail — exits 0 or 1, great for CI pipelines |
| `--spec-only / -s` | Only validate against the Agent Skills spec |
| `--all` | Validate every skill in the current directory |
| `--repo` | Validate every skill from the git repo root |
| **Scan** | |
| `sklab scan ./my-skill` | Security scan — shows BLOCK / SUS / ALLOW status per check |
| `--all` | Scan every skill in the current directory |
| **Info** | |
| `sklab info ./my-skill` | Skill metadata + token cost estimates (discovery vs activation) |
| `--json` | Output as JSON |
| `--field / -f <name>` | Extract a single field value |
| **Prompt** | |
| `sklab prompt ./skill-a` | Export skill(s) as a prompt for agent platforms |
| `--format / -f <fmt>` | Output format: `xml` (default), `markdown`, `json` |
| **Stats** | |
| `sklab stats` | Your personal usage history and score trends |
| `count` | Skill invocation counts for the current month |
| `score` | Score trend for all evaluated skills |
| `tokens` | Token usage per skill for the current month |
| **Browse** | |
| `sklab list-checks` | Browse all 33 checks across 5 dimensions |
| `--spec-only` | Only spec-required checks |
| `--suggestions-only` | Only quality suggestions |
| **Trigger Testing** _(requires `ANTHROPIC_API_KEY`)_ | |
| `sklab generate ./my-skill` | Auto-generate ~13 trigger test cases via LLM |
| `--model <model-id>` | Anthropic model ID to use (e.g. `claude-sonnet-4-6`). The skill path is a positional argument that comes before this flag. |
| `--force` | Overwrite existing test file |
| `sklab trigger ./my-skill` | Run trigger tests against a live runtime |
| `--type <type>` | Filter by type: `explicit`, `implicit`, `contextual`, `negative` |
| **Telemetry** | |
| `sklab telemetry` | Show telemetry status |
| `enable` | Enable anonymous usage telemetry |
| `disable` | Disable anonymous usage telemetry |
| `show` | View recent events (`--limit / -n N`, `--json`) |

---

## What Gets Checked

33 checks across 5 dimensions. Run `sklab list-checks` to browse all of them with severity labels.

**Structure** (11)
- SKILL.md Exists · Valid Frontmatter · Standard Frontmatter Fields
- Allowed Tools Format · Compatibility Length · License Format · Metadata Format
- Scripts Folder Valid · Scripts Self-Contained · Scripts No Interactive Input · References Folder Valid

**Naming** (3)
- Name Required · Name Format (kebab-case) · Name Matches Directory

**Description** (3)
- Description Required · Description Not Empty · Description Max Length

**Content** (11)
- Body Not Empty · Has Examples · Description Actionable · Line Budget · Token Budget
- Metadata Token Budget · Reference Depth · Asset Paths Exist · Script Paths Exist
- Scripts Referenced · Compatibility Prerequisites

**Security** (5)
- Prompt Injection & Jailbreak · Evaluator Manipulation · Unicode Obfuscation · YAML Anomalies · Suspicious Size & Structure

---

## Trigger Testing

Skill Lab generates ~13 test cases per skill across 4 types — explicit, implicit, contextual, and negative — then runs them against a live LLM via Claude CLI.

Requires Claude CLI: `npm install -g @anthropic-ai/claude-code`

```yaml
# .sklab/tests/triggers.yaml
skill: my-skill
test_cases:
  # should fire
  - id: explicit-1
    type: explicit
    prompt: "$my-skill do the thing"
    expected: trigger
  # should NOT fire
  - id: negative-1
    type: negative
    prompt: "unrelated question"
    expected: no_trigger
```

---

## Telemetry

sklab collects anonymous usage data (command names, duration, exit codes, scores, token counts). **No skill content, file paths, or flag values are ever collected.** To opt out:

```bash
sklab telemetry disable
```

See [docs/PRIVACY.md](docs/PRIVACY.md) for the full privacy policy.

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
mypy src/
ruff check src/
ruff format src/
```

---

MIT License
