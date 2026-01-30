"""Frontmatter validation checks for optional fields."""

from typing import Any, ClassVar

from skill_lab.checks.base import StaticCheck
from skill_lab.core.models import CheckResult, EvalDimension, Severity, Skill
from skill_lab.core.registry import register_check

# Maximum length for compatibility field (spec requirement)
MAX_COMPATIBILITY_LENGTH = 500


@register_check
class CompatibilityLengthCheck(StaticCheck):
    """Check that compatibility field is under 500 characters if provided."""

    check_id: ClassVar[str] = "frontmatter.compatibility-length"
    check_name: ClassVar[str] = "Compatibility Length"
    description: ClassVar[str] = "Compatibility field is under 500 characters if provided"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    spec_required: ClassVar[bool] = True

    def run(self, skill: Skill) -> CheckResult:
        if fail := self._require_metadata(skill, "check compatibility field"):
            return fail
        assert skill.metadata is not None

        raw = skill.metadata.raw
        if "compatibility" not in raw:
            return self._pass(
                "Compatibility field not present (optional)",
                location=self._skill_md_location(skill),
            )

        compatibility = raw["compatibility"]

        if not isinstance(compatibility, str):
            return self._fail(
                f"Compatibility field must be a string, got {type(compatibility).__name__}",
                details={"type": type(compatibility).__name__},
                location=self._skill_md_location(skill),
            )

        if len(compatibility) > MAX_COMPATIBILITY_LENGTH:
            return self._fail(
                f"Compatibility field exceeds {MAX_COMPATIBILITY_LENGTH} characters "
                f"(got {len(compatibility)})",
                details={
                    "length": len(compatibility),
                    "max_length": MAX_COMPATIBILITY_LENGTH,
                },
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Compatibility field is valid ({len(compatibility)} chars)",
            location=self._skill_md_location(skill),
        )


@register_check
class MetadataFormatCheck(StaticCheck):
    """Check that metadata field is a string-to-string mapping if provided."""

    check_id: ClassVar[str] = "frontmatter.metadata-format"
    check_name: ClassVar[str] = "Metadata Format"
    description: ClassVar[str] = "Metadata field is a string-to-string mapping if provided"
    severity: ClassVar[Severity] = Severity.ERROR
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    spec_required: ClassVar[bool] = True

    def run(self, skill: Skill) -> CheckResult:
        if fail := self._require_metadata(skill, "check metadata field"):
            return fail
        assert skill.metadata is not None

        raw = skill.metadata.raw
        if "metadata" not in raw:
            return self._pass(
                "Metadata field not present (optional)",
                location=self._skill_md_location(skill),
            )

        metadata_value = raw["metadata"]

        if not isinstance(metadata_value, dict):
            return self._fail(
                f"Metadata field must be a mapping, got {type(metadata_value).__name__}",
                details={"type": type(metadata_value).__name__},
                location=self._skill_md_location(skill),
            )

        # Check that all keys and values are strings
        invalid_keys: list[str] = []
        invalid_values: list[tuple[str, Any]] = []

        for key, value in metadata_value.items():
            if not isinstance(key, str):
                invalid_keys.append(repr(key))
            if not isinstance(value, str):
                invalid_values.append((str(key), type(value).__name__))

        if invalid_keys or invalid_values:
            errors: list[str] = []
            if invalid_keys:
                errors.append(f"Non-string keys: {', '.join(invalid_keys)}")
            if invalid_values:
                value_errors = [f"{k}: {t}" for k, t in invalid_values]
                errors.append(f"Non-string values: {', '.join(value_errors)}")

            return self._fail(
                "Metadata must be a string-to-string mapping; " + "; ".join(errors),
                details={
                    "invalid_keys": invalid_keys,
                    "invalid_values": [{"key": k, "type": t} for k, t in invalid_values],
                },
                location=self._skill_md_location(skill),
            )

        return self._pass(
            f"Metadata field is valid ({len(metadata_value)} entries)",
            location=self._skill_md_location(skill),
        )


@register_check
class AllowedToolsFormatCheck(StaticCheck):
    """Check that allowed-tools field is a space-delimited string if provided."""

    check_id: ClassVar[str] = "frontmatter.allowed-tools-format"
    check_name: ClassVar[str] = "Allowed Tools Format"
    description: ClassVar[str] = "Allowed-tools field is a space-delimited string if provided"
    severity: ClassVar[Severity] = Severity.WARNING  # Experimental feature
    dimension: ClassVar[EvalDimension] = EvalDimension.STRUCTURE
    spec_required: ClassVar[bool] = False  # Experimental

    def run(self, skill: Skill) -> CheckResult:
        if fail := self._require_metadata(skill, "check allowed-tools field"):
            return fail
        assert skill.metadata is not None

        raw = skill.metadata.raw
        if "allowed-tools" not in raw:
            return self._pass(
                "Allowed-tools field not present (optional)",
                location=self._skill_md_location(skill),
            )

        allowed_tools = raw["allowed-tools"]

        if not isinstance(allowed_tools, str):
            return self._fail(
                f"Allowed-tools must be a space-delimited string, got {type(allowed_tools).__name__}. "
                "Use 'tool1 tool2 tool3' format instead of a YAML list.",
                details={
                    "type": type(allowed_tools).__name__,
                    "suggestion": "Use 'allowed-tools: \"tool1 tool2 tool3\"' format",
                },
                location=self._skill_md_location(skill),
            )

        return self._pass(
            "Allowed-tools field is valid (space-delimited string)",
            location=self._skill_md_location(skill),
        )
