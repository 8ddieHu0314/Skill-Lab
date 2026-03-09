# sklab Privacy Policy

*Last updated: March 2026*

## What we collect

When telemetry is enabled (opt-out), sklab records the following data locally and syncs it to our servers:

- A random anonymous ID generated on first run. This ID is not linked to your identity, machine name, email, hostname, or any personal information.
- Command names, flags used (names only, never values), runtime duration, exit code, and whether the command succeeded.
- A session ID grouping commands run in the same terminal session.
- CLI version, operating system, and Python version.
- Whether sklab is running in a CI environment, and which CI provider if detectable.
- Skill names, skill versions, and evaluation scores when you run `sklab evaluate`.
- Token counts and model names when skills are invoked.
- Error type and the module where an error occurred (no file paths, no error messages).

## What we do not collect

- File paths or directory names
- Skill content, prompts, or outputs
- Flag values (only which flags were used, never what you passed)
- Error messages (only the exception class and module)
- Hostnames, usernames, or any system identifiers

## How we use it

Usage data helps us understand which commands are used, where errors occur, and how scores change over time. Aggregate, anonymous data may be shared publicly (e.g. "most-used commands"). We do not sell or share raw event data with third parties.

## Where it's stored

Data is stored locally at `~/.sklab/usage.db` (SQLite) and synced to a private Supabase instance.

## Retention

Local data is kept until you delete `~/.sklab/usage.db`. Server-side data has no automated deletion schedule at this time.

## How to opt out

Set `SKLAB_NO_ANALYTICS=1` or `DO_NOT_TRACK=1` in your environment before running any `sklab` command. Opt-out suppresses all local storage and server sync. Already-synced data is not retroactively deleted.

## Questions or deletion requests

Open an issue on GitHub.
