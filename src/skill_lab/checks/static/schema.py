"""Schema-based frontmatter validation.

Defines frontmatter field constraints as declarative FieldRule data.
A generic validator interprets rules and produces CheckResult objects
identical to the hand-written checks they replace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import registry


@dataclass(frozen=True)
class FieldRule:
    """A single validation rule for a frontmatter field.

    Each rule produces exactly one CheckResult, preserving the one-check-per-constraint
    granularity that the scoring system requires.
    """

    # Identity — maps 1:1 to existing check_ids
    check_id: str
    check_name: str
    description: str
    severity: Severity
    dimension: EvalDimension
    spec_required: bool = False

    # Which field to validate
    field_name: str = ""
    source: str = "raw"  # "raw" = skill.metadata.raw, "metadata" = skill.metadata attr

    # Field presence behavior
    required: bool = False
    optional_pass: bool = False

    # Type constraint
    expected_type: type[Any] | None = None
    type_error_template: str = ""

    # String constraints
    max_length: int | None = None
    not_blank: bool = False
    blank_fail_message: str = ""
    regex_pattern: str | None = None
    regex_fail_message: str = ""
    no_consecutive: str | None = None
    no_consecutive_message: str = ""

    # Dict constraints (for metadata field)
    dict_keys_type: type[Any] | None = None
    dict_values_type: type[Any] | None = None

    # Message templates
    pass_message: str = ""
    fail_message: str = ""
    absent_pass_message: str = ""
    no_metadata_context: str = "perform this check"

    # Extra details to include on type-error failure
    type_fail_details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Schema definition — the single source of truth for spec field constraints
# ---------------------------------------------------------------------------

FRONTMATTER_SCHEMA: list[FieldRule] = [
    # --- naming.required ---
    FieldRule(
        check_id="naming.required",
        check_name="Name Required",
        description="Name field is present in frontmatter",
        severity=Severity.ERROR,
        dimension=EvalDimension.NAMING,
        spec_required=True,
        field_name="name",
        source="metadata",
        required=True,
        no_metadata_context="check name",
        fail_message="Name field is missing or empty in frontmatter",
        pass_message="Name field present: '{value}'",
    ),
    # --- naming.format ---
    FieldRule(
        check_id="naming.format",
        check_name="Name Format",
        description="Name is lowercase, hyphen-separated, max 64 chars",
        severity=Severity.ERROR,
        dimension=EvalDimension.NAMING,
        spec_required=True,
        field_name="name",
        source="metadata",
        required=True,
        max_length=64,
        regex_pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
        regex_fail_message=(
            "Name must be lowercase letters, numbers, and hyphens only, "
            "and must not start or end with a hyphen"
        ),
        no_consecutive="--",
        no_consecutive_message="Name should not contain consecutive hyphens",
        no_metadata_context="validate name",
        fail_message="No name to validate",
        pass_message="Name '{value}' follows format rules",
    ),
    # --- description.required ---
    FieldRule(
        check_id="description.required",
        check_name="Description Required",
        description="Description field is present in frontmatter",
        severity=Severity.ERROR,
        dimension=EvalDimension.DESCRIPTION,
        spec_required=True,
        field_name="description",
        source="raw",
        required=True,
        no_metadata_context="check description",
        fail_message="Description field is missing from frontmatter",
        pass_message="Description field present",
    ),
    # --- description.not-empty ---
    FieldRule(
        check_id="description.not-empty",
        check_name="Description Not Empty",
        description="Description is not empty or whitespace-only",
        severity=Severity.ERROR,
        dimension=EvalDimension.DESCRIPTION,
        spec_required=True,
        field_name="description",
        source="metadata",
        not_blank=True,
        blank_fail_message="Description is empty or whitespace-only",
        pass_message="Description has content ({length} characters)",
    ),
    # --- description.max-length ---
    FieldRule(
        check_id="description.max-length",
        check_name="Description Max Length",
        description="Description is under 1024 characters",
        severity=Severity.ERROR,
        dimension=EvalDimension.DESCRIPTION,
        spec_required=True,
        field_name="description",
        source="metadata",
        max_length=1024,
        fail_message="Description exceeds {max_length} characters (got {length})",
        pass_message="Description length OK ({length}/{max_length})",
    ),
    # --- frontmatter.compatibility-length ---
    FieldRule(
        check_id="frontmatter.compatibility-length",
        check_name="Compatibility Length",
        description="Compatibility field is under 500 characters if provided",
        severity=Severity.ERROR,
        dimension=EvalDimension.STRUCTURE,
        spec_required=True,
        field_name="compatibility",
        source="raw",
        optional_pass=True,
        expected_type=str,
        type_error_template="Compatibility field must be a string, got {actual_type}",
        not_blank=True,
        blank_fail_message="Compatibility field is empty (must be 1-500 characters if provided)",
        max_length=500,
        fail_message="Compatibility field exceeds {max_length} characters (got {length})",
        pass_message="Compatibility field is valid ({length} chars)",
        absent_pass_message="Compatibility field not present (optional)",
        no_metadata_context="check compatibility field",
    ),
    # --- frontmatter.metadata-format ---
    FieldRule(
        check_id="frontmatter.metadata-format",
        check_name="Metadata Format",
        description="Metadata field is a string-to-string mapping if provided",
        severity=Severity.ERROR,
        dimension=EvalDimension.STRUCTURE,
        spec_required=True,
        field_name="metadata",
        source="raw",
        optional_pass=True,
        expected_type=dict,
        type_error_template="Metadata field must be a mapping, got {actual_type}",
        dict_keys_type=str,
        dict_values_type=str,
        pass_message="Metadata field is valid ({entry_count} entries)",
        absent_pass_message="Metadata field not present (optional)",
        no_metadata_context="check metadata field",
    ),
    # --- frontmatter.license-format ---
    FieldRule(
        check_id="frontmatter.license-format",
        check_name="License Format",
        description="License field is a string if provided",
        severity=Severity.WARNING,
        dimension=EvalDimension.STRUCTURE,
        spec_required=False,
        field_name="license",
        source="raw",
        optional_pass=True,
        expected_type=str,
        type_error_template="License field must be a string, got {actual_type}",
        pass_message="License field is valid",
        absent_pass_message="License field not present (optional)",
        no_metadata_context="check license field",
    ),
    # --- frontmatter.allowed-tools-format ---
    FieldRule(
        check_id="frontmatter.allowed-tools-format",
        check_name="Allowed Tools Format",
        description="Allowed-tools field is a space-delimited string if provided",
        severity=Severity.WARNING,
        dimension=EvalDimension.STRUCTURE,
        spec_required=False,
        field_name="allowed-tools",
        source="raw",
        optional_pass=True,
        expected_type=str,
        type_error_template=(
            "Allowed-tools must be a space-delimited string, got {actual_type}. "
            "Use 'tool1 tool2 tool3' format instead of a YAML list."
        ),
        type_fail_details={"suggestion": "Use 'allowed-tools: \"tool1 tool2 tool3\"' format"},
        pass_message="Allowed-tools field is valid (space-delimited string)",
        absent_pass_message="Allowed-tools field not present (optional)",
        no_metadata_context="check allowed-tools field",
    ),
]


# ---------------------------------------------------------------------------
# Generic validator engine
# ---------------------------------------------------------------------------


def _validate_rule(check: StaticCheck, skill: Skill, rule: FieldRule) -> CheckResult:
    """Validate a single FieldRule against a Skill, producing a CheckResult.

    This function interprets the declarative FieldRule and runs the appropriate
    validation steps, producing output identical to the hand-written checks.
    """
    location = check._skill_md_location(skill)

    # 1. No-metadata guard
    if fail := check._require_metadata(skill, rule.no_metadata_context):
        return fail
    assert skill.metadata is not None

    # 2. Extract value
    if rule.source == "raw":
        if rule.field_name not in skill.metadata.raw:
            if rule.optional_pass:
                return check._pass(rule.absent_pass_message, location=location)
            if rule.required:
                return check._fail(rule.fail_message, location=location)
        value = skill.metadata.raw[rule.field_name]
    else:  # source == "metadata"
        value = getattr(skill.metadata, rule.field_name, "")

    # 3. Required-absent (for metadata-source fields where empty = absent)
    if rule.source == "metadata" and rule.required and not value:
        # naming.format has a special fail message for missing name
        return check._fail(rule.fail_message, location=location)

    # 4. Type check
    if rule.expected_type is not None and not isinstance(value, rule.expected_type):
        actual_type = type(value).__name__
        message = rule.type_error_template.format(actual_type=actual_type)
        details: dict[str, Any] = {"type": actual_type}
        if rule.type_fail_details:
            details.update(rule.type_fail_details)
        return check._fail(message, details=details, location=location)

    # 5. Not-blank check (for string values)
    if rule.not_blank and isinstance(value, str) and not value.strip():
        return check._fail(rule.blank_fail_message, location=location)

    # 6. Dict key/value validation (metadata-format special path)
    if (rule.dict_keys_type is not None or rule.dict_values_type is not None) and isinstance(
        value, dict
    ):
        return _validate_dict(check, value, rule, location)

    # 7. Accumulate constraint errors (for naming.format multi-error pattern)
    errors: list[str] = []

    if rule.max_length is not None and isinstance(value, str) and len(value) > rule.max_length:
        if rule.regex_pattern is not None or rule.no_consecutive is not None:
            # Multi-error accumulation mode (naming.format)
            errors.append(f"Name exceeds {rule.max_length} characters (got {len(value)})")
        else:
            # Single-error mode (description.max-length, compatibility)
            length = len(value)
            message = rule.fail_message.format(
                length=length, max_length=rule.max_length, value=value
            )
            return check._fail(
                message,
                details={"length": length, "max_length": rule.max_length},
                location=location,
            )

    if (
        rule.regex_pattern is not None
        and isinstance(value, str)
        and not re.match(rule.regex_pattern, value)
    ):
        errors.append(rule.regex_fail_message)

    if rule.no_consecutive is not None and isinstance(value, str) and rule.no_consecutive in value:
        errors.append(rule.no_consecutive_message)

    if errors:
        return check._fail(
            "; ".join(errors),
            details={"name": value, "errors": errors},
            location=location,
        )

    # 8. Pass
    if isinstance(value, str):
        message = rule.pass_message.format(
            value=value, length=len(value), max_length=rule.max_length or 0
        )
    elif isinstance(value, dict):
        message = rule.pass_message.format(entry_count=len(value))
    else:
        message = rule.pass_message.format(value=value)

    return check._pass(message, location=location)


def _validate_dict(
    check: StaticCheck,
    value: dict[Any, Any],
    rule: FieldRule,
    location: str,
) -> CheckResult:
    """Validate dict key/value types (metadata-format check)."""
    invalid_keys: list[str] = []
    invalid_values: list[tuple[str, str]] = []

    for k, v in value.items():
        if rule.dict_keys_type is not None and not isinstance(k, rule.dict_keys_type):
            invalid_keys.append(repr(k))
        if rule.dict_values_type is not None and not isinstance(v, rule.dict_values_type):
            invalid_values.append((str(k), type(v).__name__))

    if invalid_keys or invalid_values:
        error_parts: list[str] = []
        if invalid_keys:
            error_parts.append(f"Non-string keys: {', '.join(invalid_keys)}")
        if invalid_values:
            value_errors = [f"{k}: {t}" for k, t in invalid_values]
            error_parts.append(f"Non-string values: {', '.join(value_errors)}")

        return check._fail(
            "Metadata must be a string-to-string mapping; " + "; ".join(error_parts),
            details={
                "invalid_keys": invalid_keys,
                "invalid_values": [{"key": k, "type": t} for k, t in invalid_values],
            },
            location=location,
        )

    message = rule.pass_message.format(entry_count=len(value))
    return check._pass(message, location=location)


# ---------------------------------------------------------------------------
# Dynamic class factory
# ---------------------------------------------------------------------------


def _make_schema_check(rule: FieldRule) -> type[StaticCheck]:
    """Create a concrete StaticCheck subclass from a FieldRule."""
    # Capture rule in closure
    _rule = rule

    class _SchemaCheck(StaticCheck):
        check_id: ClassVar[str] = _rule.check_id
        check_name: ClassVar[str] = _rule.check_name
        description: ClassVar[str] = _rule.description
        severity: ClassVar[Severity] = _rule.severity
        dimension: ClassVar[EvalDimension] = _rule.dimension
        spec_required: ClassVar[bool] = _rule.spec_required

        def run(self, skill: Skill) -> CheckResult:
            return _validate_rule(self, skill, _rule)

    # Descriptive name for debugging
    safe_id = _rule.check_id.replace(".", "_").replace("-", "_")
    _SchemaCheck.__name__ = f"SchemaCheck_{safe_id}"
    _SchemaCheck.__qualname__ = _SchemaCheck.__name__
    return _SchemaCheck


# ---------------------------------------------------------------------------
# Registration — runs on import, same pattern as @register_check
# ---------------------------------------------------------------------------


def _register_schema_checks() -> None:
    """Register all schema-defined checks with the global registry."""
    for rule in FRONTMATTER_SCHEMA:
        check_class = _make_schema_check(rule)
        registry.register(check_class)


_register_schema_checks()
