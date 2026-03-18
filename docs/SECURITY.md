# Security Scanning

`sklab scan` runs a five-layer static security check on a skill and returns one of three statuses:

| Status | Meaning |
|--------|---------|
| **ALLOW** | No findings |
| **SUS** | Size/structure anomalies only (Layer A) |
| **BLOCK** | Any finding from Layers B–E |

`sklab validate` also runs the security scan — a BLOCK fails validation; SUS does not.

---

## Layer A — Size / Structure

Flags anomalies that suggest payload stuffing or obfuscation via bulk content. Findings here produce **SUS**, not **BLOCK**, unless combined with findings from other layers.

| Check | Threshold |
|-------|-----------|
| Body exceeds maximum size | > 100 KB |
| Single line exceeds maximum length | > 2,000 chars |
| Repeated character sequences | Same char repeated 10+ times |
| Excessive blank lines | > 60% of lines are whitespace-only |

---

## Layer B — Unicode / Obfuscation

Detects characters and word constructions used to hide malicious content from human reviewers while remaining executable by the model.

**Invisible / control characters**

Flags zero-width characters (`U+200B`, `U+200C`, `U+200D`, `U+FEFF`, `U+2060`), bidirectional override characters (`U+202A`–`U+202E`, `U+2066`–`U+2069`), and ASCII control characters (`U+0001`–`U+0008`, `U+000E`–`U+001F`) — but only when found **within 50 characters** of a risky keyword.

The proximity window exists because these characters appear legitimately in real content: `U+200D` (ZWJ) is used in emoji sequences, `U+200C` (ZWNJ) in Indic and Persian text, and `U+FEFF` is often present as a BOM in copy-pasted web content. Flagging every occurrence would produce constant false positives on harmless skills. The window narrows the signal to cases where the character is plausibly being used to split or obscure an attack phrase.

Risky keywords that trigger the proximity check:

`ignore` · `disregard` · `bypass` · `exfiltrate` · `jailbreak` · `instruction` / `instructions` · `system prompt` · `developer mode` · `unrestricted` · `safety` · `restriction` / `restrictions` · `guidelines` · `claude`

**Homoglyph detection**

Tokenises the NFKC-normalised body and flags any word that mixes ASCII letters with Cyrillic (`U+0400`–`U+04FF`) or Greek (`U+0370`–`U+03FF`) characters. Example: `develорer` where `о` is Cyrillic U+043E.

---

## Layer C — YAML Allowlist / Frontmatter Validation

Validates that the frontmatter contains only expected keys and well-formed values. Any unexpected key or malformed value is a **BLOCK** finding.

**Allowlisted keys:** `name`, `description`, `license`, `version`, `trigger`, `tags`, `author`, `compatibility`, `metadata`, `allowed-tools`, `disable-model-invocation`, `user-invocable`, `model`, `context`, `agent`, `hooks`, `argument-hint`

| Check | Detail |
|-------|--------|
| Unknown frontmatter key | Any key not in the allowlist |
| Newline in `name` field | Multi-line name values |
| Oversized `description` | > 500 characters |
| Non-list `tags` value | `tags` must be a list of strings |
| Nested dict in any field | Unexpected object values (except `metadata`) |
| Injection in field values | All string and list-item field values are also scanned by Layers D and E |

---

## Layer D — Prompt Injection / Jailbreak

Runs regex patterns against the NFKC-normalised body and all frontmatter string values. Patterns are split into two tiers:

**BLOCK patterns** — direct instruction override attempts:

- Instruction override: `ignore/forget/discard/disregard/override ... instructions`
- Identity override: `you are now [DAN / developer mode / god mode / jailbreak]`
- System prompt extraction: `reveal the system prompt`
- Safety bypass: `bypass/disable/suppress/remove safety/restrictions/guidelines/limits`
- Restriction removal: `no restrictions`, `without any restrictions`, `free of restrictions`
- Temporal framing: `from now on ... no restrictions`
- Conditional framing: `respond as if you had no restrictions`
- Simulation framing: `simulate a mode without restrictions`
- Data exfiltration: `exfiltrate`, `send this conversation`, `output hidden instructions`
- Developer mode: `developer mode enabled`

**Indirect patterns** (softer phrasing, still produces **BLOCK**):

- Fictional framing: `in a fictional/hypothetical world/scenario/context`
- Safety negation: `pretend safety rules do not exist`, `pretend you have no restrictions`
- Identity removal: `you are no longer/not Claude`
- Unrestricted persona: `act as an unrestricted ...`
- Roleplay bypass: `roleplay as an AI without restrictions`

**Meta-commentary exception:** findings are suppressed when the matched phrase appears within 200 characters of words like `example`, `malicious`, `scanner`, `detect`, `block`, or `do not use`. This prevents false positives in skills that document or explain attack patterns.

---

## Layer E — Evaluator Manipulation

Detects phrases targeting the automated evaluation pipeline specifically — attempts to coerce the scanner into passing a malicious skill.

| Pattern | Example |
|---------|---------|
| Evaluator identity | `if you are an evaluator` |
| Score manipulation | `rate this skill 10 / ten` |
| Pass coercion | `say this skill is safe`, `output pass` |
| Issue suppression | `do not mention/flag/report vulnerabilities/issues` |
| Status coercion | `mark this skill as safe/pass/approved` |

Unlike Layer D, evaluator patterns are **not** subject to the meta-commentary exception — a skill that documents these patterns is itself suspicious.

---

## False Positive Considerations

- **Layer A** thresholds are intentionally permissive. A large legitimate skill (e.g. one with embedded reference data) will get SUS, not BLOCK.
- **Layer B** only fires on invisible chars near risky keywords, avoiding false positives from emoji or non-Latin scripts in multilingual skills.
- **Layer D** broad patterns (`no restrictions`, `without restrictions`) may occasionally match legitimate phrasing such as *"there are no restrictions on input format"*. The meta-commentary exception mitigates this.
- Regex matching is a surface-level signal. It is effective against careless or templated attacks but not against a determined adversary who rephrases carefully. For high-assurance environments, complement `sklab scan` with a semantic LLM-based review pass.
