"""Security scanning check for skills.

Runs five layers and maps findings to one of three statuses:

    BLOCK — any finding from layers B–E (unicode, YAML, injection, evaluator)
    SUS   — findings from layer A only (size / structure anomalies)
    ALLOW — no findings

Each finding carries: problem description, source location, exact line text.

Layer order:
    A — Size / structure
    B — Unicode normalization + invisible/bidi char scan + homoglyph detection
    C — YAML allowlist + type validation (also scans field values)
    D — Prompt injection / jailbreak regex  (on NFKC-normalised text)
    E — Evaluator-manipulation regex        (on NFKC-normalised text)
"""

import re
import unicodedata
from typing import Any, ClassVar, TypedDict

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill, SkillMetadata
from skill_lab.core.registry import register_check


class Finding(TypedDict):
    """A single security finding with location and exact source text."""

    problem: str  # human-readable description of the issue
    location: str  # e.g. "line 12" or "frontmatter.system_prompt"
    text: str  # exact line or field value where the issue was found


# ─── Layer A: Size / structure ────────────────────────────────────────────────

_MAX_BODY_BYTES = 100_000  # 100 KB
_MAX_LINE_CHARS = 2_000
_REPEATED_TOKEN_RE = re.compile(r"(.)\1{9,}")  # same char repeated 10+ times
_WHITESPACE_LINE_RATIO = 0.60  # > 60% whitespace-only lines

# ─── Layer B: Unicode / obfuscation ──────────────────────────────────────────

_ZERO_WIDTH: frozenset[str] = frozenset({"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"})

_BIDI_OVERRIDES: frozenset[str] = frozenset(
    {chr(c) for c in range(0x202A, 0x202F)} | {chr(c) for c in range(0x2066, 0x206A)}
)

_CONTROL_CHARS: frozenset[str] = frozenset(
    {chr(c) for c in range(0x0001, 0x0009)} | {chr(c) for c in range(0x000E, 0x0020)}
)

_SUSPICIOUS_UNICODE: frozenset[str] = _ZERO_WIDTH | _BIDI_OVERRIDES | _CONTROL_CHARS

_RISKY_KEYWORD_RE = re.compile(
    r"ignore|disregard|bypass|exfiltrate|jailbreak|instructions?|system.?prompt|"
    r"developer.?mode|unrestricted|safety|restrictions?|guidelines?|claude",
    re.IGNORECASE,
)


def _is_ascii_alpha(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z")


def _is_cyrillic(c: str) -> bool:
    return "\u0400" <= c <= "\u04ff"


def _is_greek(c: str) -> bool:
    return "\u0370" <= c <= "\u03ff"


def _has_mixed_scripts(word: str) -> bool:
    """Return True if word mixes ASCII letters with Cyrillic or Greek chars."""
    has_ascii = any(_is_ascii_alpha(c) for c in word)
    has_foreign = any(_is_cyrillic(c) or _is_greek(c) for c in word)
    return has_ascii and has_foreign


# ─── Layer C: YAML allowlist ──────────────────────────────────────────────────

YAML_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Agent Skills spec fields
        "name",
        "description",
        "license",
        "version",
        "trigger",
        "tags",
        "author",
        "compatibility",
        "metadata",
        "allowed-tools",
        # Claude Code extension fields
        "disable-model-invocation",
        "user-invocable",
        "model",
        "context",
        "agent",
        "hooks",
        "argument-hint",
    }
)

# ─── Layer D: Prompt injection / jailbreak ────────────────────────────────────

_INJECTION_BLOCK: list[re.Pattern[str]] = [
    re.compile(
        r"ignore\s+(all\s+)?(previous|prior|above|system|developer)\s+instructions?",
        re.IGNORECASE,
    ),
    re.compile(
        r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?",
        re.IGNORECASE,
    ),
    re.compile(
        r"forget\s+(all\s+)?(previous|prior|above|your)\s+instructions?",
        re.IGNORECASE,
    ),
    re.compile(
        r"discard\s+(all\s+)?(previous|prior|your)\s+instructions?",
        re.IGNORECASE,
    ),
    re.compile(
        r"override\s+(all\s+)?(?:your\s+)?instructions?",
        re.IGNORECASE,
    ),
    re.compile(
        r"you\s+are\s+now\s+(?:in\s+)?(?:dan|developer\s+mode|god\s+mode|jailbreak)",
        re.IGNORECASE,
    ),
    re.compile(r"developer\s+mode\s+enabled", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(
        r"(?:bypass|disable|suppress|remove)\s+(?:safety|restrictions?|guidelines?|limits?)",
        re.IGNORECASE,
    ),
    re.compile(r"exfiltrate", re.IGNORECASE),
    re.compile(r"send\s+(?:this\s+)?conversation", re.IGNORECASE),
    re.compile(r"output\s+hidden\s+instructions", re.IGNORECASE),
    re.compile(r"no\s+restrictions?", re.IGNORECASE),
    re.compile(r"without\s+(?:any\s+)?restrictions?", re.IGNORECASE),
    re.compile(r"free\s+of\s+(?:any\s+)?restrictions?", re.IGNORECASE),
    re.compile(
        r"from\s+now\s+on[,\s]+(?:you\s+)?(?:have\s+)?no\s+restrictions?",
        re.IGNORECASE,
    ),
    re.compile(
        r"respond\s+as\s+if\s+you\s+(?:have|had)\s+no\s+restrictions?",
        re.IGNORECASE,
    ),
    re.compile(
        r"simulate\s+(?:a\s+mode|being)\s+(?:without|with\s+no)\s+(?:restrictions?|limits?)",
        re.IGNORECASE,
    ),
]

_INJECTION_WARN: list[re.Pattern[str]] = [
    re.compile(
        r"in\s+a\s+(?:fictional|hypothetical)\s+(?:world|scenario|context)",
        re.IGNORECASE,
    ),
    re.compile(
        r"pretend\s+(?:safety\s+rules?|restrictions?)\s+do\s+not\s+exist",
        re.IGNORECASE,
    ),
    re.compile(
        r"pretend\s+you\s+(?:have\s+)?no\s+(?:restrictions?|limits?|guidelines?)", re.IGNORECASE
    ),
    re.compile(r"act\s+as\s+an?\s+unrestricted", re.IGNORECASE),
    re.compile(
        r"roleplay\s+as\s+an?\s+(?:ai|assistant)\s+(?:without|with\s+no)\s+(?:restrictions?|limits?)",
        re.IGNORECASE,
    ),
    re.compile(r"you\s+are\s+(?:no\s+longer|not)\s+claude", re.IGNORECASE),
]

_META_COMMENTARY_RE = re.compile(
    r"detect|block|example|malicious|security|do\s+not\s+use|scanner",
    re.IGNORECASE,
)
_META_COMMENTARY_WINDOW = 200

# ─── Layer E: Evaluator-manipulation ─────────────────────────────────────────

_EVALUATOR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"if\s+you\s+are\s+(?:an?\s+)?evaluat(?:or|ing)", re.IGNORECASE),
    re.compile(r"rate\s+this\s+skill\s+(?:10|ten)", re.IGNORECASE),
    re.compile(r"say\s+this\s+(?:skill\s+)?is\s+safe", re.IGNORECASE),
    re.compile(r"output\s+pass", re.IGNORECASE),
    re.compile(
        r"do\s+not\s+(?:mention|flag|report)\s+(?:vulnerabilit|issue|problem)",
        re.IGNORECASE,
    ),
    re.compile(
        r"mark\s+(?:this\s+)?(?:skill\s+)?(?:as\s+)?(?:safe|pass|approved)",
        re.IGNORECASE,
    ),
]

# ─── Shared helpers ───────────────────────────────────────────────────────────


def _line_of(body: str, pos: int) -> tuple[int, str]:
    """Return (1-based line number, stripped line text) for a position in body."""
    before = body[:pos]
    line_num = before.count("\n") + 1
    line_start = before.rfind("\n") + 1
    line_end = body.find("\n", pos)
    line_text = body[line_start : line_end if line_end != -1 else len(body)]
    return line_num, line_text.strip()


def _is_near_meta_commentary(text: str, match_start: int, match_end: int) -> bool:
    lo = max(0, match_start - _META_COMMENTARY_WINDOW)
    hi = min(len(text), match_end + _META_COMMENTARY_WINDOW)
    return bool(_META_COMMENTARY_RE.search(text[lo:hi]))


# ─── Layer implementations ────────────────────────────────────────────────────


def _check_size(body: str) -> list[Finding]:
    findings: list[Finding] = []

    byte_size = len(body.encode("utf-8"))
    if byte_size > _MAX_BODY_BYTES:
        findings.append(
            Finding(
                problem=f"Body exceeds 100 KB ({byte_size // 1024} KB)",
                location="file",
                text=f"{byte_size // 1024} KB total",
            )
        )

    lines = body.splitlines()

    for i, line in enumerate(lines):
        if len(line) > _MAX_LINE_CHARS:
            findings.append(
                Finding(
                    problem=f"Line exceeds {_MAX_LINE_CHARS} chars ({len(line)} chars)",
                    location=f"line {i + 1}",
                    text=line[:120] + ("…" if len(line) > 120 else ""),
                )
            )

    m = _REPEATED_TOKEN_RE.search(body)
    if m:
        line_num, line_text = _line_of(body, m.start())
        findings.append(
            Finding(
                problem="Repeated token patterns (possible DoS payload)",
                location=f"line {line_num}",
                text=line_text[:120] + ("…" if len(line_text) > 120 else ""),
            )
        )

    if lines:
        whitespace_count = sum(1 for line in lines if not line.strip())
        if whitespace_count / len(lines) > _WHITESPACE_LINE_RATIO:
            findings.append(
                Finding(
                    problem=f"Excessive whitespace-only lines ({whitespace_count}/{len(lines)})",
                    location="file",
                    text=f"{whitespace_count} blank lines out of {len(lines)}",
                )
            )

    return findings


def _check_unicode(body: str) -> list[Finding]:
    findings: list[Finding] = []

    for i, c in enumerate(body):
        if c in _SUSPICIOUS_UNICODE:
            window = body[max(0, i - 50) : i + 50]
            if _RISKY_KEYWORD_RE.search(window):
                line_num, line_text = _line_of(body, i)
                findings.append(
                    Finding(
                        problem=f"Suspicious unicode character (U+{ord(c):04X}) near risky keyword",
                        location=f"line {line_num}",
                        text=repr(line_text[:80])[1:-1],  # show escape sequences
                    )
                )
                break  # one finding per block of suspicious chars

    normalised = unicodedata.normalize("NFKC", body)
    for m in re.finditer(r"\b\w+\b", normalised):
        word = m.group()
        if _has_mixed_scripts(word):
            line_num, line_text = _line_of(body, m.start())
            findings.append(
                Finding(
                    problem=f"Homoglyph word (mixed scripts): '{word}'",
                    location=f"line {line_num}",
                    text=line_text,
                )
            )

    return findings


def _match_patterns(
    patterns: list[re.Pattern[str]],
    text: str,
    normalised: str,
    source_label: str,
    problem_prefix: str,
    *,
    check_meta_commentary: bool = False,
) -> list[Finding]:
    """Scan normalised text against a pattern list and return findings."""
    findings: list[Finding] = []
    for pattern in patterns:
        for m in pattern.finditer(normalised):
            if check_meta_commentary and _is_near_meta_commentary(normalised, m.start(), m.end()):
                continue
            line_num, line_text = _line_of(text, m.start())
            findings.append(
                Finding(
                    problem=f"{problem_prefix}: '{m.group()[:60]}'",
                    location=source_label
                    if source_label.startswith("frontmatter")
                    else f"line {line_num}",
                    text=line_text,
                )
            )
    return findings


def _scan_text_for_injections(
    text: str, source_label: str, normalised: str | None = None
) -> list[Finding]:
    """Run Layer D (injection block + warn) patterns against a text string."""
    if normalised is None:
        normalised = unicodedata.normalize("NFKC", text)
    return _match_patterns(
        _INJECTION_BLOCK,
        text,
        normalised,
        source_label,
        "Prompt injection",
        check_meta_commentary=True,
    ) + _match_patterns(
        _INJECTION_WARN,
        text,
        normalised,
        source_label,
        "Jailbreak pattern",
        check_meta_commentary=True,
    )


def _scan_text_for_evaluator(
    text: str, source_label: str, normalised: str | None = None
) -> list[Finding]:
    """Run Layer E (evaluator-manipulation) patterns against a text string."""
    if normalised is None:
        normalised = unicodedata.normalize("NFKC", text)
    return _match_patterns(
        _EVALUATOR_PATTERNS,
        text,
        normalised,
        source_label,
        "Evaluator manipulation",
    )


def _check_yaml(metadata: SkillMetadata | None) -> list[Finding]:
    if metadata is None:
        return []

    findings: list[Finding] = []
    raw = metadata.raw

    for key in sorted(set(raw.keys()) - YAML_ALLOWLIST):
        val = raw[key]
        findings.append(
            Finding(
                problem=f"Unexpected YAML key: '{key}'",
                location=f"frontmatter.{key}",
                text=f"{key}: {str(val)[:80]}",
            )
        )

    name_val = raw.get("name")
    if isinstance(name_val, str) and "\n" in name_val:
        findings.append(
            Finding(
                problem="'name' field contains newlines",
                location="frontmatter.name",
                text=repr(name_val[:80]),
            )
        )

    desc_val = raw.get("description")
    if isinstance(desc_val, str) and len(desc_val) > 500:
        findings.append(
            Finding(
                problem=f"'description' field exceeds 500 chars ({len(desc_val)} chars)",
                location="frontmatter.description",
                text=desc_val[:80] + "…",
            )
        )

    tags_val = raw.get("tags")
    if tags_val is not None and not isinstance(tags_val, list):
        findings.append(
            Finding(
                problem="'tags' field must be a list of strings",
                location="frontmatter.tags",
                text=f"tags: {str(tags_val)[:80]}",
            )
        )

    for key, val in raw.items():
        if key != "metadata" and isinstance(val, dict):
            findings.append(
                Finding(
                    problem=f"Unexpected nested dict in frontmatter field '{key}'",
                    location=f"frontmatter.{key}",
                    text=f"{key}: {{…}}",
                )
            )

    for key, val in raw.items():
        if isinstance(val, str) and val.strip():
            label = f"frontmatter.{key}"
            val_normalised = unicodedata.normalize("NFKC", val)
            findings.extend(_scan_text_for_injections(val, label, normalised=val_normalised))
            findings.extend(_scan_text_for_evaluator(val, label, normalised=val_normalised))

    return findings


def _check_injection(body: str, normalised: str) -> list[Finding]:
    return _scan_text_for_injections(body, "body", normalised=normalised)


def _check_evaluator(body: str, normalised: str) -> list[Finding]:
    return _scan_text_for_evaluator(body, "body", normalised=normalised)


# ─── Registered check ─────────────────────────────────────────────────────────


@register_check
class SecurityScanCheck(StaticCheck):
    """Composite security scan across five layers.

    Status:
        BLOCK (ERROR)   — any finding from layers B–E
        SUS   (WARNING) — findings from layer A only (size/structure)
        ALLOW           — no findings
    """

    check_id: ClassVar[str] = "security.scan"
    check_name: ClassVar[str] = "Security Scan"
    description: ClassVar[str] = (
        "Scans the skill for prompt injection, jailbreak patterns, unicode obfuscation, "
        "YAML anomalies, and evaluator-manipulation attempts"
    )
    severity: ClassVar[Severity] = Severity.HIGH
    dimension: ClassVar[EvalDimension] = EvalDimension.SECURITY
    fix: ClassVar[str] = (
        "Remove prompt injection, jailbreak, evaluator-manipulation, and unicode obfuscation "
        "patterns from the skill body and frontmatter"
    )

    def run(self, skill: Skill) -> CheckResult:
        body = skill.body or ""
        normalised = unicodedata.normalize("NFKC", body)

        size_findings = _check_size(body)
        other_findings = (
            _check_unicode(body)
            + _check_yaml(skill.metadata)
            + _check_injection(body, normalised)
            + _check_evaluator(body, normalised)
        )
        all_findings = size_findings + other_findings

        if other_findings:
            status = "block"
        elif size_findings:
            status = "sus"
        else:
            status = "allow"

        details: dict[str, Any] = {"status": status, "findings": all_findings}

        if status == "block":
            return self._fail(
                f"Security scan blocked: {other_findings[0]['problem']}",
                details=details,
            )
        if status == "sus":
            return CheckResult(
                check_id=self.check_id,
                check_name=self.check_name,
                passed=False,
                severity=Severity.MEDIUM,
                dimension=self.dimension,
                message=f"Security scan suspicious: {size_findings[0]['problem']}",
                details=details,
                fix=self.fix,
            )
        return self._pass("Security scan passed", details=details)
