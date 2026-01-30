# Skill-Lab Quality Checks

This document lists all 23 static checks used to evaluate agent skills, aligned with the [Agent Skills Specification](https://agentskills.io/specification).

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

**Quality suggestions (13):** Additional checks for best practices that improve skill quality but aren't required by the spec.

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

## Structure Checks (8)

| Check ID | Severity | Spec | Description |
|----------|----------|------|-------------|
| `structure.skill-md-exists` | ERROR | Required | SKILL.md file exists in the skill directory |
| `structure.valid-frontmatter` | ERROR | Required | YAML frontmatter is parseable and valid |
| `frontmatter.compatibility-length` | ERROR | Required | Compatibility field is under 500 characters if provided |
| `frontmatter.metadata-format` | ERROR | Required | Metadata field is a string-to-string mapping if provided |
| `frontmatter.allowed-tools-format` | WARNING | - | Allowed-tools field is a space-delimited string if provided |
| `structure.scripts-valid` | WARNING | - | /scripts contains only valid script files |
| `structure.references-valid` | WARNING | - | /references contains only valid reference files |
| `structure.no-unexpected-files` | INFO | - | No unexpected files in skill root directory |

### Details

**structure.skill-md-exists** (Spec: Required)
- Checks that `SKILL.md` exists (uppercase required)
- Fails if only lowercase `skill.md` is found

**structure.valid-frontmatter** (Spec: Required)
- Verifies YAML frontmatter can be parsed
- Fails if frontmatter is missing or malformed

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

**structure.scripts-valid** (Quality suggestion)
- Optional folder - passes if not present
- Valid extensions: `.py`, `.sh`, `.js`, `.ts`, `.bash`

**structure.references-valid** (Quality suggestion)
- Optional folder - passes if not present
- Valid extensions: `.md`, `.txt`, `.rst`

**structure.no-unexpected-files** (Quality suggestion)
- Expected items: `SKILL.md`, `skill.md`, `scripts`, `references`, `assets`
- Hidden files (starting with `.`) are ignored

---

## Naming Checks (4)

| Check ID | Severity | Spec | Description |
|----------|----------|------|-------------|
| `naming.required` | ERROR | Required | Name field is present in frontmatter |
| `naming.format` | ERROR | Required | Name is lowercase, hyphen-separated, max 64 chars |
| `naming.matches-directory` | ERROR | Required | Name must match the parent directory name |
| `naming.no-reserved` | WARNING | - | Name does not contain 'anthropic', 'claude', etc. |

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

**naming.no-reserved** (Quality suggestion)
- Reserved words: `anthropic`, `claude`, `openai`, `gpt`
- Case-insensitive matching

---

## Description Checks (5)

| Check ID | Severity | Spec | Description |
|----------|----------|------|-------------|
| `description.required` | ERROR | Required | Description field is present in frontmatter |
| `description.not-empty` | ERROR | Required | Description is not empty (1-1024 chars) |
| `description.max-length` | ERROR | Required | Description is under 1024 characters |
| `description.third-person` | INFO | - | Description uses third-person voice |
| `description.includes-triggers` | INFO | Recommended | Description describes when to use the skill |

### Details

**description.required** (Spec: Required)
- Description field must exist in frontmatter

**description.not-empty** (Spec: Required)
- Must contain non-whitespace content (1-1024 characters per spec)

**description.max-length** (Spec: Required)
- Maximum 1024 characters

**description.third-person** (Quality suggestion)
- Fails if first-person patterns detected: `I will`, `I can`, `I am`, `I'm`, `I've`, `my`, `me`
- Should use third-person (e.g., "Creates files..." not "I create files...")

**description.includes-triggers** (Spec: Recommended)
- Per spec: description "should describe when to use it"
- Looks for trigger keywords: `when`, `if`, `trigger`, `activate`, `invoke`, `use when/for/to`

---

## Content Checks (6)

| Check ID | Severity | Spec | Description |
|----------|----------|------|-------------|
| `content.body-not-empty` | WARNING | - | SKILL.md body has meaningful content (min 50 chars) |
| `content.line-budget` | WARNING | Recommended | Body is under 500 lines |
| `content.has-examples` | INFO | Recommended | Content contains code examples |
| `content.no-windows-paths` | INFO | - | Content does not contain Windows-style paths |
| `content.no-time-sensitive` | INFO | - | Content does not contain hardcoded dates |
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

**content.no-windows-paths** (Quality suggestion)
- Detects patterns like `C:\` or `\\`
- Use forward slashes for cross-platform compatibility

**content.no-time-sensitive** (Quality suggestion)
- Detects hardcoded dates: `2024-01-15`, `1/15/2024`, `January 15, 2024`
- Filters out version numbers (e.g., `1.0.0`)

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
