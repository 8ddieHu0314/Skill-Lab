# sklab Privacy Policy

*Last updated: March 2026*

## What we collect

When telemetry is enabled (opt-out), sklab records the following data locally and syncs it to our servers:

- A random anonymous ID generated on first run. This ID is not linked to your identity, machine name, email, hostname, or any personal information.
- Command names, flags used (names only, never values), runtime duration, exit code, and whether the command succeeded.
- A session ID grouping commands run in the same terminal session.
- CLI version, operating system, and Python version.
- Whether sklab is running in a CI environment, and which CI provider if detectable.
- Evaluation scores, token counts, and model names (aggregated, without skill identity).
- Error type and the module where an error occurred (no file paths, no error messages).

## Local-only fields

The following fields are stored in the local SQLite database but are **never synced** to the server:

- `skill_path` — absolute path to the skill directory
- `skill_name` — name from SKILL.md frontmatter
- `skill_version` — version from SKILL.md frontmatter
- `skill_source` — source identifier (e.g., local, marketplace)

## What we do not collect

- File paths or directory names (local-only, see above)
- Skill content, prompts, or outputs
- Flag values (only which flags were used, never what you passed)
- Error messages (only the exception class and module)
- Hostnames, usernames, or any system identifiers

## How we use it

Usage data helps us understand which commands are used, where errors occur, and how scores change over time. Aggregate, anonymous data may be shared publicly (e.g. "most-used commands"). We do not sell or share raw event data with third parties.

## Where it's stored

Data is stored locally at `~/.sklab/usage.db` (SQLite) and synced to a private Supabase instance.

## Retention

- **Local:** Rows older than 90 days are automatically deleted. Run `sklab telemetry purge` for an immediate wipe.
- **Server:** Retained for 12 months, then permanently deleted.

## How to opt out

Set `SKLAB_NO_ANALYTICS=1` or `DO_NOT_TRACK=1` in your environment before running any `sklab` command. Opt-out suppresses all local storage and server sync. Already-synced data is not retroactively deleted.

You can also manage telemetry via CLI commands:

```bash
sklab telemetry status   # View current telemetry configuration
sklab telemetry disable  # Disable telemetry
sklab telemetry enable   # Re-enable telemetry
sklab telemetry purge    # Delete all local telemetry data
sklab telemetry show     # View recent events
```

## Audit mode

Set `SKLAB_TELEMETRY_DEBUG=1` to print the exact JSON payload that would be sent to the server (to stderr). The network POST is skipped in debug mode — use this to audit exactly what data is collected.

## Questions or deletion requests

Open an issue on GitHub.
