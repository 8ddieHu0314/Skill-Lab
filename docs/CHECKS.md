# Skill-Lab Quality Checks

This document lists all 20 static checks used to evaluate agent skills.

## Scoring

**Dimension Weights:**
- Structure: 30%
- Naming: 20%
- Description: 25%
- Content: 25%

**Severity Weights:**
- ERROR: 1.0 (must fix)
- WARNING: 0.5 (should fix)
- INFO: 0.25 (suggestion)

---

## Structure Checks (5)

| Check ID | Severity | Description |
|----------|----------|-------------|
| `structure.skill-md-exists` | ERROR | SKILL.md file exists in the skill directory |
| `structure.valid-frontmatter` | ERROR | YAML frontmatter is parseable and valid |
| `structure.scripts-valid` | WARNING | /scripts contains only .py, .sh, .js, .ts, .bash files |
| `structure.references-valid` | WARNING | /references contains only .md, .txt, .rst files |
| `structure.no-unexpected-files` | INFO | No unexpected files in skill root directory |

### Details

**structure.skill-md-exists**
- Checks that `SKILL.md` exists (uppercase required)
- Fails if only lowercase `skill.md` is found

**structure.valid-frontmatter**
- Verifies YAML frontmatter can be parsed
- Fails if frontmatter is missing or malformed

**structure.scripts-valid**
- Optional folder - passes if not present
- Valid extensions: `.py`, `.sh`, `.js`, `.ts`, `.bash`

**structure.references-valid**
- Optional folder - passes if not present
- Valid extensions: `.md`, `.txt`, `.rst`

**structure.no-unexpected-files**
- Expected items: `SKILL.md`, `skill.md`, `scripts`, `references`, `assets`
- Hidden files (starting with `.`) are ignored

---

## Naming Checks (4)

| Check ID | Severity | Description |
|----------|----------|-------------|
| `naming.required` | ERROR | Name field is present in frontmatter |
| `naming.format` | ERROR | Name is lowercase, hyphen-separated, max 64 chars |
| `naming.no-reserved` | ERROR | Name does not contain 'anthropic', 'claude', 'openai', 'gpt' |
| `naming.gerund-convention` | WARNING | Name uses gerund form (e.g., 'creating-docs') |

### Details

**naming.required**
- Name field must be present and non-empty in frontmatter

**naming.format**
- Must match pattern: `^[a-z][a-z0-9-]*[a-z0-9]$` or single letter `^[a-z]$`
- Maximum 64 characters
- No consecutive hyphens (`--`)

**naming.no-reserved**
- Reserved words: `anthropic`, `claude`, `openai`, `gpt`
- Case-insensitive matching

**naming.gerund-convention**
- Name should start with a gerund verb (ending in `-ing`)
- Common prefixes: `creating`, `building`, `managing`, `handling`, `processing`, `generating`, `analyzing`, `converting`, `formatting`, `validating`, `testing`, `deploying`, `configuring`, `monitoring`, `debugging`, `optimizing`, `implementing`, `developing`, `writing`, `reading`, `updating`, `deleting`, `searching`, `filtering`, `sorting`, `parsing`, `rendering`, `fetching`, `sending`, `receiving`, `authenticating`, `authorizing`

---

## Description Checks (5)

| Check ID | Severity | Description |
|----------|----------|-------------|
| `description.required` | ERROR | Description field is present in frontmatter |
| `description.not-empty` | ERROR | Description is not empty or whitespace-only |
| `description.max-length` | ERROR | Description is under 1024 characters |
| `description.third-person` | WARNING | Description uses third-person voice |
| `description.includes-triggers` | WARNING | Description describes when to use the skill |

### Details

**description.required**
- Description field must exist in frontmatter

**description.not-empty**
- Must contain non-whitespace content

**description.max-length**
- Maximum 1024 characters

**description.third-person**
- Fails if first-person patterns detected: `I will`, `I can`, `I am`, `I'm`, `I've`, `my`, `me`
- Should use third-person (e.g., "Creates files..." not "I create files...")

**description.includes-triggers**
- Should contain trigger keywords: `when`, `if`, `trigger`, `activate`, `invoke`, `use when/for/to`
- Helps clarify when the skill should be activated

---

## Content Checks (6)

| Check ID | Severity | Description |
|----------|----------|-------------|
| `content.body-not-empty` | ERROR | SKILL.md body has meaningful content (min 50 chars) |
| `content.line-budget` | WARNING | Body is under 500 lines |
| `content.has-examples` | INFO | Content contains code examples |
| `content.no-windows-paths` | WARNING | Content does not contain Windows-style paths |
| `content.no-time-sensitive` | WARNING | Content does not contain hardcoded dates |
| `content.reference-depth` | WARNING | References are max 1 level deep |

### Details

**content.body-not-empty**
- Body must have at least 50 characters of content

**content.line-budget**
- Maximum 500 lines in body

**content.has-examples**
- Looks for fenced code blocks (` ``` `), indented code (4+ spaces), or `<example>` tags

**content.no-windows-paths**
- Detects patterns like `C:\` or `\\`
- Use forward slashes for cross-platform compatibility

**content.no-time-sensitive**
- Detects hardcoded dates: `2024-01-15`, `1/15/2024`, `January 15, 2024`
- Filters out version numbers (e.g., `1.0.0`)

**content.reference-depth**
- References folder should not have nested subdirectories beyond 1 level
