# Skill-Lab Quality Checks

This document lists all checks used to evaluate agent skills:
- **19 Static Checks**: Validate SKILL.md structure, naming, description, and content
- **5 Trace Check Types**: Validate execution traces (command presence, file creation, sequences, loops, efficiency)

Static checks are aligned with the [Agent Skills Specification](https://agentskills.io/specification).

## Filtering Checks

You can choose to run only spec-required checks (skipping quality suggestions):

```bash
# Evaluate with spec-required checks only
sklab evaluate ./my-skill --spec-only

# Validate with spec-required checks only
sklab validate ./my-skill --spec-only

# List only spec-required checks
sklab list-checks --spec-only

# List only quality suggestion checks
sklab list-checks --suggestions-only
```

**Spec-required checks (10):** Must pass to be considered a valid Agent Skill per the specification.

**Quality suggestions (9):** Additional checks for best practices that improve skill quality but aren't required by the spec.

---

## Scoring

**Dimension Weights:**
- Structure: 30%
- Naming: 20%
- Description: 25%
- Content: 25%

**Severity Levels:**
- **ERROR** (weight: 1.0) - Spec requirement, must fix
- **WARNING** (weight: 0.5) - Spec recommendation, should fix
- **INFO** (weight: 0.25) - Quality suggestion, nice to have

---

## Structure Checks (9)

| Check ID | Severity | Spec | Description |
|----------|----------|------|-------------|
| `structure.skill-md-exists` | ERROR | Required | SKILL.md file exists in the skill directory |
| `structure.valid-frontmatter` | ERROR | Required | YAML frontmatter is parseable and valid |
| `structure.standard-frontmatter-fields` | WARNING | - | Frontmatter contains only spec-defined fields |
| `frontmatter.compatibility-length` | ERROR | Required | Compatibility field is under 500 characters if provided |
| `frontmatter.metadata-format` | ERROR | Required | Metadata field is a string-to-string mapping if provided |
| `frontmatter.allowed-tools-format` | WARNING | - | Allowed-tools field is a space-delimited string if provided |
| `frontmatter.license-format` | WARNING | - | License field is a valid string if provided |
| `structure.scripts-valid` | WARNING | - | /scripts contains only valid script files |
| `structure.references-valid` | WARNING | - | /references contains only valid reference files |

### Details

**structure.skill-md-exists** (Spec: Required)
- Checks that `SKILL.md` exists (uppercase required)
- Fails if only lowercase `skill.md` is found

**structure.valid-frontmatter** (Spec: Required)
- Verifies YAML frontmatter can be parsed
- Fails if frontmatter is missing or malformed

**structure.standard-frontmatter-fields** (Quality suggestion)
- Warns when frontmatter contains fields not defined in the Agent Skills spec
- Spec-defined fields: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`
- Non-standard fields (e.g., `argument-hint`, `context`, `agent`) may cause unexpected behavior across different agent implementations
- Custom fields should be placed in the `metadata` map instead

**frontmatter.compatibility-length** (Spec: Required)
- Validates the optional `compatibility` field if present
- Maximum 500 characters per spec
- Passes if field is not present (optional field)

**frontmatter.metadata-format** (Spec: Required)
- Validates the optional `metadata` field if present
- Must be a string-to-string mapping (key-value pairs)
- All keys must be strings, all values must be strings
- Passes if field is not present (optional field)

**frontmatter.allowed-tools-format** (Quality suggestion - experimental)
- Validates the optional `allowed-tools` field if present
- Must be a space-delimited string (e.g., `"Read Write Bash"`)
- Common mistake: using YAML list syntax instead of string
- Passes if field is not present (optional field)

**frontmatter.license-format** (Quality suggestion)
- Validates the optional `license` field if present
- Must be a non-empty string
- Passes if field is not present (optional field)

**structure.scripts-valid** (Quality suggestion)
- Optional folder - passes if not present
- Valid extensions: `.py`, `.sh`, `.js`, `.ts`, `.bash`

**structure.references-valid** (Quality suggestion)
- Optional folder - passes if not present
- Valid extensions: `.md`, `.txt`, `.rst`

---

## Naming Checks (3)

| Check ID | Severity | Spec | Description |
|----------|----------|------|-------------|
| `naming.required` | ERROR | Required | Name field is present in frontmatter |
| `naming.format` | ERROR | Required | Name is lowercase, hyphen-separated, max 64 chars |
| `naming.matches-directory` | ERROR | Required | Name must match the parent directory name |

### Details

**naming.required** (Spec: Required)
- Name field must be present and non-empty in frontmatter

**naming.format** (Spec: Required)
- Must be 1-64 characters
- May only contain lowercase letters, numbers, and hyphens (`a-z`, `0-9`, `-`)
- Must not start or end with a hyphen
- Must not contain consecutive hyphens (`--`)

**naming.matches-directory** (Spec: Required)
- The `name` field must exactly match the parent directory name
- Example: If directory is `pdf-processing/`, name must be `pdf-processing`

---

## Description Checks (3)

| Check ID | Severity | Spec | Description |
|----------|----------|------|-------------|
| `description.required` | ERROR | Required | Description field is present in frontmatter |
| `description.not-empty` | ERROR | Required | Description is not empty (1-1024 chars) |
| `description.max-length` | ERROR | Required | Description is under 1024 characters |

### Details

**description.required** (Spec: Required)
- Description field must exist in frontmatter

**description.not-empty** (Spec: Required)
- Must contain non-whitespace content (1-1024 characters per spec)

**description.max-length** (Spec: Required)
- Maximum 1024 characters

> **Note:** Trigger keyword validation (`description.includes-triggers`) was removed because static regex matching produces false positives on semantically clear descriptions. This will be reimplemented as an LLM-as-judge check in a future release.

---

## Content Checks (4)

| Check ID | Severity | Spec | Description |
|----------|----------|------|-------------|
| `content.body-not-empty` | WARNING | - | SKILL.md body has meaningful content (min 50 chars) |
| `content.line-budget` | WARNING | Recommended | Body is under 500 lines |
| `content.has-examples` | INFO | Recommended | Content contains code examples |
| `content.reference-depth` | WARNING | Recommended | References are max 1 level deep |

### Details

**content.body-not-empty** (Quality suggestion)
- Body should have at least 50 characters of content
- Note: Spec allows empty body, but this is rarely useful

**content.line-budget** (Spec: Recommended)
- Per spec: "Keep your main SKILL.md under 500 lines"
- Maximum 500 lines in body

**content.has-examples** (Spec: Recommended)
- Per spec: "Examples of inputs and outputs" are recommended
- Looks for fenced code blocks (` ``` `), indented code (4+ spaces), or `<example>` tags

**content.reference-depth** (Spec: Recommended)
- Per spec: "Keep file references one level deep from SKILL.md"
- References folder should not have nested subdirectories beyond 1 level

---

## Specification Reference

Based on the [Agent Skills Specification](https://agentskills.io/specification):

### Required Fields
| Field | Constraints |
|-------|-------------|
| `name` | 1-64 chars, lowercase alphanumeric + hyphens, no start/end hyphen, no `--`, must match directory |
| `description` | 1-1024 chars, non-empty |

### Optional Fields
| Field | Constraints |
|-------|-------------|
| `license` | License name or reference to bundled file |
| `compatibility` | Max 500 chars, environment requirements |
| `metadata` | Key-value map for additional properties |
| `allowed-tools` | Space-delimited list (experimental) |

### Directory Structure
```
skill-name/
├── SKILL.md          # Required
├── scripts/          # Optional - executable code
├── references/       # Optional - additional documentation
└── assets/           # Optional - static resources
```

---

## Trace Checks (5 Types)

Trace checks analyze execution traces (JSONL) to validate skill behavior. Define checks in `tests/trace_checks.yaml`.

```bash
sklab eval-trace ./my-skill --trace ./execution.jsonl
```

| Check Type | Description | Required Fields |
|------------|-------------|-----------------|
| `command_presence` | Verify a command was executed | `pattern` |
| `file_creation` | Verify a file was created | `path` |
| `event_sequence` | Verify commands ran in order | `sequence` |
| `loop_detection` | Detect excessive command repetition | `max_retries` (default: 3) |
| `efficiency` | Check command count limits | `max_commands` |

### Example Definition

```yaml
# tests/trace_checks.yaml
checks:
  - id: npm-install-ran
    type: command_presence
    pattern: "npm install"

  - id: package-json-created
    type: file_creation
    path: "package.json"

  - id: correct-sequence
    type: event_sequence
    sequence: ["npm init", "npm install", "npm run build"]

  - id: no-excessive-retries
    type: loop_detection
    max_retries: 3

  - id: command-count-limit
    type: efficiency
    max_commands: 20
```

### Check Details

**command_presence**
- Searches trace for commands matching the `pattern` (substring match)
- Passes if at least one matching command was executed

**file_creation**
- Checks if the specified `path` exists after execution
- Path is relative to the skill directory

**event_sequence**
- Verifies commands were executed in the specified order
- All commands in `sequence` must appear, in order (not necessarily consecutive)

**loop_detection**
- Detects if any command was repeated more than `max_retries` times
- Helps catch thrashing or infinite retry loops

**efficiency**
- Fails if total command count exceeds `max_commands`
- Useful for ensuring skills don't run excessive operations
