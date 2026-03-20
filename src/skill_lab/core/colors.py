"""Brand color palette for the sklab CLI.

Single source of truth for all terminal colors used across reporters,
commands, and the CLI framework. Change a value here to rebrand everywhere.
"""

# ── Brand accent colors ──────────────────────────────────────────────────────

ACCENT = "#d4ff4e"  # Acid yellow — commands, key columns, paths, spinners
SECONDARY = "#c084fc"  # Purple — flags, sub-items, secondary columns
BORDER = "#94bf0e"  # Dark acid green — panel borders

# ── Semantic status colors ────────────────────────────────────────────────────

PASS_COLOR = ACCENT  # Success — PASS, OK, score ≥80, all-passed summaries
FAIL_COLOR = "red"  # Failure — FAIL, errors, score <60
WARN_COLOR = "yellow"  # Warning — partial pass, score 60–79, SUS status
NEUTRAL_COLOR = "white"  # Fallback for unknown severity

# ── Score delta colors ────────────────────────────────────────────────────────

DELTA_POSITIVE = "green"  # Score improved
DELTA_NEGATIVE = "red"  # Score regressed

# ── Banner gradient (top → bottom) ───────────────────────────────────────────

BANNER_GRADIENT = [
    "#d4ff4e",
    "#c4ef3e",
    "#b4df2e",
    "#a4cf1e",
    "#94bf0e",
    "#84af00",
]

# ── Severity styles (keyed by Severity.value) ────────────────────────────────

SEVERITY_STYLES: dict[str, str] = {
    "high": f"bold {FAIL_COLOR}",
    "medium": WARN_COLOR,
    "low": "blue",
}
