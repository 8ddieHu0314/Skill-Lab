"""Tests for static checks."""

from pathlib import Path

import pytest

from skill_lab.checks.static.content import (
    BodyNotEmptyCheck,
    CompatibilityPrereqsCheck,
    HasExamplesCheck,
    LineBudgetCheck,
    ScriptPathsExistCheck,
    ScriptsReferencedCheck,
)
from skill_lab.checks.static.naming import (
    NameMatchesDirectoryCheck,
)
from skill_lab.checks.static.structure import (
    ScriptsNoInteractiveCheck,
    ScriptsSelfContainedCheck,
    ScriptsValidCheck,
    SkillMdExistsCheck,
    StandardFrontmatterFieldsCheck,
    ValidFrontmatterCheck,
)
from skill_lab.checks.static.schema import FRONTMATTER_SCHEMA
from skill_lab.checks.static.structure import SPEC_FRONTMATTER_FIELDS
from skill_lab.core.models import Severity, Skill, SkillMetadata
from skill_lab.core.registry import registry

# Ensure schema checks are registered
from skill_lab.checks.static import schema as _schema  # noqa: F401


def _get_check(check_id: str):
    """Get a check instance from the registry by ID."""
    check_class = registry.get(check_id)
    assert check_class is not None, f"Check '{check_id}' not found in registry"
    return check_class()


def make_skill(
    name: str = "test-skill",
    description: str = "A test skill description",
    body: str = "This is the skill body content with enough text.",
    parse_errors: tuple = (),
    path: Path | None = None,
) -> Skill:
    """Helper to create a Skill for testing."""
    return Skill(
        path=path or Path("/test/skill"),
        metadata=SkillMetadata(name=name, description=description, raw={"name": name, "description": description}),
        body=body,
        has_scripts=False,
        has_references=False,
        has_assets=False,
        parse_errors=parse_errors,
    )


class TestStructureChecks:
    """Tests for structure checks."""

    def test_skill_md_exists_pass(self, valid_skill_path: Path):
        check = SkillMdExistsCheck()
        skill = Skill(
            path=valid_skill_path,
            metadata=None,
            body="",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_valid_frontmatter_pass(self):
        check = ValidFrontmatterCheck()
        skill = make_skill()
        result = check.run(skill)
        assert result.passed

    def test_valid_frontmatter_fail_no_metadata(self):
        check = ValidFrontmatterCheck()
        skill = Skill(
            path=Path("/test"),
            metadata=None,
            body="Body",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed

    def test_standard_frontmatter_fields_pass(self):
        """Test that standard spec fields pass."""
        check = StandardFrontmatterFieldsCheck()
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "license": "MIT",
                    "compatibility": "Requires Python 3.10+",
                    "metadata": {"author": "test"},
                    "allowed-tools": "Read Write Bash",
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed
        assert result.severity == Severity.WARNING

    def test_standard_frontmatter_fields_fail_non_standard(self):
        """Test that non-standard fields trigger a warning."""
        check = StandardFrontmatterFieldsCheck()
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "argument-hint": "[topic]",  # non-standard
                    "disable-model-invocation": True,  # non-standard
                    "context": "fork",  # non-standard
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.WARNING
        assert "argument-hint" in result.message
        assert "context" in result.message
        assert "disable-model-invocation" in result.message

    def test_standard_frontmatter_fields_no_metadata(self):
        """Test that missing metadata passes (nothing to check)."""
        check = StandardFrontmatterFieldsCheck()
        skill = Skill(
            path=Path("/test"),
            metadata=None,
            body="Body",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed


class TestNamingChecks:
    """Tests for naming checks."""

    def test_name_required_pass(self):
        check = _get_check("naming.required")
        skill = make_skill(name="my-skill")
        result = check.run(skill)
        assert result.passed

    def test_name_required_fail(self):
        check = _get_check("naming.required")
        skill = make_skill(name="")
        result = check.run(skill)
        assert not result.passed

    def test_name_format_valid(self):
        check = _get_check("naming.format")
        # Per spec: lowercase alphanumeric + hyphens, no start/end hyphen
        for valid_name in ["my-skill", "skill123", "a", "creating-reports", "30daysresearch", "123", "1"]:
            skill = make_skill(name=valid_name)
            result = check.run(skill)
            assert result.passed, f"Expected '{valid_name}' to pass"

    def test_name_format_invalid(self):
        check = _get_check("naming.format")
        # Invalid: uppercase, underscores, spaces, start/end with hyphen, consecutive hyphens
        for invalid_name in ["My_Skill", "UPPERCASE", "spaces here", "-starts-with-hyphen", "ends-with-hyphen-", "has--consecutive-hyphens"]:
            skill = make_skill(name=invalid_name)
            result = check.run(skill)
            assert not result.passed, f"Expected '{invalid_name}' to fail"

    def test_name_matches_directory_pass(self):
        check = NameMatchesDirectoryCheck()
        skill = make_skill(name="my-skill", path=Path("/test/my-skill"))
        result = check.run(skill)
        assert result.passed

    def test_name_matches_directory_fail(self):
        check = NameMatchesDirectoryCheck()
        skill = make_skill(name="different-name", path=Path("/test/my-skill"))
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.ERROR

    def test_name_matches_directory_unicode_normalization(self):
        """NFKC normalization: precomposed and decomposed forms should match."""
        check = NameMatchesDirectoryCheck()
        # caf\u00e9 (precomposed) as name, cafe\u0301 (decomposed) as directory
        skill = make_skill(name="caf\u00e9", path=Path("/test/cafe\u0301"))
        result = check.run(skill)
        assert result.passed


class TestDescriptionChecks:
    """Tests for description checks."""

    def test_description_required_pass(self):
        check = _get_check("description.required")
        skill = make_skill(description="Some description")
        result = check.run(skill)
        assert result.passed

    def test_description_not_empty_pass(self):
        check = _get_check("description.not-empty")
        skill = make_skill(description="Valid description")
        result = check.run(skill)
        assert result.passed

    def test_description_not_empty_fail(self):
        check = _get_check("description.not-empty")
        skill = make_skill(description="   ")
        result = check.run(skill)
        assert not result.passed

    def test_description_max_length_pass(self):
        check = _get_check("description.max-length")
        skill = make_skill(description="Short description")
        result = check.run(skill)
        assert result.passed

    def test_description_max_length_fail(self):
        check = _get_check("description.max-length")
        skill = make_skill(description="x" * 2000)
        result = check.run(skill)
        assert not result.passed



class TestContentChecks:
    """Tests for content checks."""

    def test_body_not_empty_pass(self):
        check = BodyNotEmptyCheck()
        skill = make_skill(body="This is some meaningful content that is long enough to pass the minimum requirement.")
        result = check.run(skill)
        assert result.passed

    def test_body_not_empty_fail(self):
        check = BodyNotEmptyCheck()
        skill = make_skill(body="")
        result = check.run(skill)
        assert not result.passed
        assert result.severity == Severity.WARNING  # Quality suggestion, spec allows empty body

    def test_body_too_short(self):
        check = BodyNotEmptyCheck()
        skill = make_skill(body="Short")
        result = check.run(skill)
        assert not result.passed

    def test_line_budget_pass(self):
        check = LineBudgetCheck()
        skill = make_skill(body="Line 1\nLine 2\nLine 3")
        result = check.run(skill)
        assert result.passed

    def test_line_budget_fail(self):
        check = LineBudgetCheck()
        skill = make_skill(body="\n".join(["Line"] * 600))
        result = check.run(skill)
        assert not result.passed

    def test_has_examples_pass(self):
        check = HasExamplesCheck()
        skill = make_skill(body="# Title\n\n```python\ncode here\n```")
        result = check.run(skill)
        assert result.passed

    def test_has_examples_fail(self):
        check = HasExamplesCheck()
        skill = make_skill(body="Just text without any code examples.")
        result = check.run(skill)
        assert not result.passed


class TestFrontmatterChecks:
    """Tests for optional frontmatter field checks."""

    def test_compatibility_valid(self):
        check = _get_check("frontmatter.compatibility-length")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "compatibility": "Requires Python 3.10+",
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_compatibility_too_long(self):
        check = _get_check("frontmatter.compatibility-length")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "compatibility": "x" * 501,  # Over 500 chars
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "exceeds" in result.message

    def test_compatibility_empty_fails(self):
        """Spec requires 1-500 characters if provided."""
        check = _get_check("frontmatter.compatibility-length")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "compatibility": "",  # Empty string
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "empty" in result.message.lower()

    def test_compatibility_whitespace_only_fails(self):
        """Whitespace-only compatibility should fail."""
        check = _get_check("frontmatter.compatibility-length")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "compatibility": "   ",  # Whitespace only
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed

    def test_metadata_valid(self):
        check = _get_check("frontmatter.metadata-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "metadata": {"author": "test-org", "version": "1.0"},
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_metadata_non_string_value_fails(self):
        check = _get_check("frontmatter.metadata-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "metadata": {"author": "test-org", "version": 1.0},  # Number instead of string
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "string" in result.message.lower()

    def test_allowed_tools_valid(self):
        check = _get_check("frontmatter.allowed-tools-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "allowed-tools": "Read Write Bash",
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_allowed_tools_list_fails(self):
        """Using YAML list syntax instead of space-delimited string should fail."""
        check = _get_check("frontmatter.allowed-tools-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "allowed-tools": ["Read", "Write", "Bash"],  # List instead of string
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "space-delimited" in result.message.lower()

    def test_license_valid_string(self):
        check = _get_check("frontmatter.license-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "license": "Apache-2.0",
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert result.passed

    def test_license_absent_passes(self):
        check = _get_check("frontmatter.license-format")
        skill = make_skill()
        result = check.run(skill)
        assert result.passed

    def test_license_non_string_fails(self):
        """YAML can parse 'license: true' as boolean."""
        check = _get_check("frontmatter.license-format")
        skill = Skill(
            path=Path("/test/my-skill"),
            metadata=SkillMetadata(
                name="my-skill",
                description="A test skill",
                raw={
                    "name": "my-skill",
                    "description": "A test skill",
                    "license": True,  # Boolean instead of string
                },
            ),
            body="Body content",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        result = check.run(skill)
        assert not result.passed
        assert "string" in result.message.lower()


def _make_tmp_skill(
    tmp_path: Path,
    body: str = "Skill body content with enough text to pass checks.",
    name: str = "test-skill",
    description: str = "A test skill",
    compatibility: str | None = None,
) -> Skill:
    """Create a Skill object rooted at tmp_path with a real filesystem."""
    raw: dict[str, object] = {"name": name, "description": description}
    if compatibility is not None:
        raw["compatibility"] = compatibility
    return Skill(
        path=tmp_path,
        metadata=SkillMetadata(name=name, description=description, raw=raw),
        body=body,
        has_scripts=(tmp_path / "scripts").is_dir(),
        has_references=False,
        has_assets=False,
    )


class TestScriptChecks:
    """Tests for script-related checks (6 new checks)."""

    # ── structure.scripts-valid: .rb extension fix ──────────────────────

    def test_scripts_valid_accepts_ruby(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "helper.rb").write_text("puts 'hello'")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsValidCheck().run(skill)
        assert result.passed

    # ── content.scripts-referenced ──────────────────────────────────────

    def test_scripts_referenced_no_scripts_dir(self, tmp_path: Path):
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsReferencedCheck().run(skill)
        assert result.passed

    def test_scripts_referenced_empty_scripts_dir(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir()
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsReferencedCheck().run(skill)
        assert result.passed

    def test_scripts_referenced_mentioned_in_body(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "deploy.sh").write_text("#!/bin/bash")
        skill = _make_tmp_skill(tmp_path, body="Run scripts/deploy.sh to deploy.")
        result = ScriptsReferencedCheck().run(skill)
        assert result.passed
        assert "deploy.sh" in result.message

    def test_scripts_referenced_fail_not_mentioned(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "deploy.sh").write_text("#!/bin/bash")
        (scripts / "setup.py").write_text("import os")
        skill = _make_tmp_skill(tmp_path, body="No mention of any scripts here.")
        result = ScriptsReferencedCheck().run(skill)
        assert not result.passed
        assert result.severity == Severity.WARNING

    # ── content.script-paths-exist ──────────────────────────────────────

    def test_script_paths_exist_no_refs(self, tmp_path: Path):
        skill = _make_tmp_skill(tmp_path, body="No script references here.")
        result = ScriptPathsExistCheck().run(skill)
        assert result.passed

    def test_script_paths_exist_all_resolve(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "run.py").write_text("print('hi')")
        skill = _make_tmp_skill(tmp_path, body="Execute scripts/run.py to start.")
        result = ScriptPathsExistCheck().run(skill)
        assert result.passed

    def test_script_paths_exist_missing(self, tmp_path: Path):
        skill = _make_tmp_skill(tmp_path, body="Run scripts/missing.py to start.")
        result = ScriptPathsExistCheck().run(skill)
        assert not result.passed
        assert "scripts/missing.py" in result.message

    def test_script_paths_exist_mixed(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "found.sh").write_text("#!/bin/bash")
        skill = _make_tmp_skill(
            tmp_path,
            body="Run scripts/found.sh and scripts/gone.sh to deploy.",
        )
        result = ScriptPathsExistCheck().run(skill)
        assert not result.passed
        assert "scripts/gone.sh" in result.message

    def test_script_paths_exist_ruby_extension(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "helper.rb").write_text("puts 'hi'")
        skill = _make_tmp_skill(tmp_path, body="Use scripts/helper.rb for help.")
        result = ScriptPathsExistCheck().run(skill)
        assert result.passed

    def test_script_paths_exist_ignores_prefixed_paths(self, tmp_path: Path):
        """'my-scripts/tool.py' and './scripts/tool.py' should NOT match."""
        skill = _make_tmp_skill(
            tmp_path,
            body="See my-scripts/tool.py and ./scripts/other.py for details.",
        )
        result = ScriptPathsExistCheck().run(skill)
        assert result.passed  # No references detected → PASS

    # ── structure.scripts-no-interactive ─────────────────────────────────

    def test_scripts_no_interactive_no_scripts(self, tmp_path: Path):
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert result.passed

    def test_scripts_no_interactive_clean_scripts(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "clean.py").write_text("print('hello')\n")
        (scripts / "clean.sh").write_text("echo hello\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert result.passed

    def test_scripts_no_interactive_commented_python(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "ok.py").write_text("# input('this is a comment')\nprint('ok')\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert result.passed

    def test_scripts_no_interactive_python_input(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "bad.py").write_text("name = input('Enter name: ')\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "bad.py" in result.message

    def test_scripts_no_interactive_shell_read(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "bad.sh").write_text("#!/bin/bash\nread -p 'Name: ' name\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "bad.sh" in result.message

    def test_scripts_no_interactive_js_readline(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "bad.js").write_text("const rl = readline.createInterface();\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "bad.js" in result.message

    def test_scripts_no_interactive_ruby_gets(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "bad.rb").write_text("name = gets.chomp\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "bad.rb" in result.message

    def test_scripts_no_interactive_commented_js(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "ok.js").write_text("// readline is not used\nconsole.log('ok');\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert result.passed

    def test_scripts_no_interactive_shell_select(self, tmp_path: Path):
        """Shell 'select' builtin should be detected."""
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "menu.sh").write_text('#!/bin/bash\nselect opt in "a" "b"; do echo $opt; done\n')
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "menu.sh" in result.message

    def test_scripts_no_interactive_python_select_no_false_positive(self, tmp_path: Path):
        """Python string containing 'select' should NOT trigger (language-specific patterns)."""
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "ok.py").write_text('print("Create or select a project")\n')
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert result.passed

    def test_scripts_no_interactive_python_getpass(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "auth.py").write_text("import getpass\npw = getpass.getpass('Password: ')\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "auth.py" in result.message

    def test_scripts_no_interactive_ruby_stdin_gets(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "ask.rb").write_text("line = STDIN.gets\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "ask.rb" in result.message

    def test_scripts_no_interactive_js_process_stdin(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "read.js").write_text("process.stdin.on('data', (d) => {});\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "read.js" in result.message

    def test_scripts_no_interactive_js_prompt(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "ask.js").write_text("const answer = prompt('Question?');\n")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsNoInteractiveCheck().run(skill)
        assert not result.passed
        assert "ask.js" in result.message

    # ── structure.scripts-self-contained ─────────────────────────────────

    def test_scripts_self_contained_no_scripts(self, tmp_path: Path):
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsSelfContainedCheck().run(skill)
        assert result.passed

    def test_scripts_self_contained_no_manifests(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "run.py").write_text("print('hi')")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsSelfContainedCheck().run(skill)
        assert result.passed

    def test_scripts_self_contained_fail_requirements(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "requirements.txt").write_text("requests==2.31.0")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsSelfContainedCheck().run(skill)
        assert not result.passed
        assert result.severity == Severity.INFO
        assert "requirements.txt" in result.message

    def test_scripts_self_contained_fail_package_json(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "package.json").write_text('{"name": "scripts"}')
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsSelfContainedCheck().run(skill)
        assert not result.passed
        assert "package.json" in result.message

    def test_scripts_self_contained_fail_gemfile(self, tmp_path: Path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "Gemfile").write_text("source 'https://rubygems.org'")
        skill = _make_tmp_skill(tmp_path)
        result = ScriptsSelfContainedCheck().run(skill)
        assert not result.passed
        assert "Gemfile" in result.message

    # ── content.compatibility-prereqs ───────────────────────────────────

    def test_compatibility_prereqs_no_runners(self, tmp_path: Path):
        skill = _make_tmp_skill(tmp_path, body="Just normal text.")
        result = CompatibilityPrereqsCheck().run(skill)
        assert result.passed

    def test_compatibility_prereqs_npx_with_nodejs(self, tmp_path: Path):
        skill = _make_tmp_skill(
            tmp_path,
            body="Use npx create-react-app to scaffold.",
            compatibility="Requires Node.js 18+",
        )
        result = CompatibilityPrereqsCheck().run(skill)
        assert result.passed

    def test_compatibility_prereqs_uvx_with_uv(self, tmp_path: Path):
        skill = _make_tmp_skill(
            tmp_path,
            body="Run uvx ruff check .",
            compatibility="Requires uv",
        )
        result = CompatibilityPrereqsCheck().run(skill)
        assert result.passed

    def test_compatibility_prereqs_npx_without_compat(self, tmp_path: Path):
        skill = _make_tmp_skill(
            tmp_path,
            body="Use npx create-react-app to scaffold.",
        )
        result = CompatibilityPrereqsCheck().run(skill)
        assert not result.passed
        assert result.severity == Severity.INFO
        assert "npx" in result.message
        assert "Node.js" in result.message

    def test_compatibility_prereqs_multiple_missing(self, tmp_path: Path):
        skill = _make_tmp_skill(
            tmp_path,
            body="Use npx for JS and uvx for Python tools.",
        )
        result = CompatibilityPrereqsCheck().run(skill)
        assert not result.passed
        assert "npx" in result.message
        assert "uvx" in result.message


class TestSchemaSync:
    """Verify that SPEC_FRONTMATTER_FIELDS stays in sync with FRONTMATTER_SCHEMA."""

    def test_spec_fields_cover_all_raw_schema_fields(self):
        """Every field_name with source='raw' in FRONTMATTER_SCHEMA should be a spec field."""
        schema_raw_fields = {
            rule.field_name for rule in FRONTMATTER_SCHEMA if rule.source == "raw"
        }
        missing = schema_raw_fields - SPEC_FRONTMATTER_FIELDS
        assert not missing, (
            f"FRONTMATTER_SCHEMA has raw fields not in SPEC_FRONTMATTER_FIELDS: {missing}. "
            f"Add them to SPEC_FRONTMATTER_FIELDS in structure.py."
        )

    def test_spec_fields_cover_all_metadata_schema_fields(self):
        """Every field_name with source='metadata' should also be a spec field."""
        schema_meta_fields = {
            rule.field_name for rule in FRONTMATTER_SCHEMA if rule.source == "metadata"
        }
        missing = schema_meta_fields - SPEC_FRONTMATTER_FIELDS
        assert not missing, (
            f"FRONTMATTER_SCHEMA has metadata fields not in SPEC_FRONTMATTER_FIELDS: {missing}. "
            f"Add them to SPEC_FRONTMATTER_FIELDS in structure.py."
        )
