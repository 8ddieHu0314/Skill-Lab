"""Unit tests for failure analyzer functionality."""

from pathlib import Path

import pytest

from skill_lab.core.models import (
    Skill,
    SkillMetadata,
    TriggerExpectation,
    TriggerResult,
    TriggerTestCase,
    TriggerType,
)
from skill_lab.triggers.failure_analyzer import FailureAnalyzer


class TestFailureAnalyzer:
    """Tests for the FailureAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> FailureAnalyzer:
        """Create a FailureAnalyzer instance."""
        return FailureAnalyzer()

    @pytest.fixture
    def sample_skill(self) -> Skill:
        """Create a sample skill for testing."""
        return Skill(
            path=Path("/test/skill"),
            metadata=SkillMetadata(
                name="write-commit-message",
                description=(
                    "Drafts git commit messages following conventional commit format. "
                    "Use when the user asks to write, draft, or compose a commit message."
                ),
                raw={},
            ),
            body="# Write Commit Message\n\nDraft commit messages.",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )

    def _make_test_case(
        self,
        prompt: str,
        trigger_type: TriggerType = TriggerType.NEGATIVE,
        expected_trigger: bool = False,
    ) -> TriggerTestCase:
        """Helper to create test cases."""
        return TriggerTestCase(
            id="test-1",
            name="Test case",
            skill_name="write-commit-message",
            prompt=prompt,
            trigger_type=trigger_type,
            expected=TriggerExpectation(skill_triggered=expected_trigger),
        )

    def _make_result(
        self,
        expected_trigger: bool,
        skill_triggered: bool,
    ) -> TriggerResult:
        """Helper to create test results."""
        return TriggerResult(
            test_id="test-1",
            test_name="Test case",
            trigger_type=TriggerType.NEGATIVE,
            passed=False,
            skill_triggered=skill_triggered,
            expected_trigger=expected_trigger,
            message="Test failed",
        )


class TestFalsePositiveAnalysis(TestFailureAnalyzer):
    """Tests for false positive (triggered when shouldn't) analysis."""

    def test_keyword_overlap_detection(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test detection of keyword overlap between prompt and description."""
        test_case = self._make_test_case(
            prompt="Commit these changes to the repository",
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        assert analysis.failure_type == "false_positive"
        assert "commit" in analysis.matching_keywords
        # Root cause could be keyword_overlap or missing_exclusion (if execution verb detected)
        assert analysis.root_cause in ("keyword_overlap", "missing_exclusion")

    def test_execution_verb_detection(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test detection of execution verbs without drafting verbs."""
        test_case = self._make_test_case(
            prompt="Run git commit on these files",
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        assert analysis.failure_type == "false_positive"
        # Should suggest adding exclusion clause
        suggestion_texts = [s.description.lower() for s in analysis.suggestions]
        assert any("exclusion" in t or "execute" in t for t in suggestion_texts)

    def test_inline_content_detection(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test detection of inline content (e.g., -m 'message')."""
        test_case = self._make_test_case(
            prompt="Run git commit -m 'fix: resolve login bug'",
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        assert analysis.failure_type == "false_positive"
        assert analysis.root_cause == "inline_content"

    def test_informational_query_detection(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test detection of informational queries."""
        test_case = self._make_test_case(
            prompt="How do I write a good commit message?",
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        assert analysis.failure_type == "false_positive"
        assert analysis.root_cause == "informational_query"

    def test_likely_test_bug_detection(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test detection of likely test bugs (wrong expectation)."""
        # This prompt has multiple keyword matches and drafting intent
        test_case = self._make_test_case(
            prompt="Help me write a commit message for my changes",
            trigger_type=TriggerType.NEGATIVE,
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        # Should flag as likely test bug since it clearly should trigger
        assert analysis.is_likely_test_bug is True


class TestFalseNegativeAnalysis(TestFailureAnalyzer):
    """Tests for false negative (didn't trigger when should) analysis."""

    def test_missing_keywords_detection(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test detection of missing keywords in description."""
        test_case = self._make_test_case(
            prompt="Help me phrase my save message for version control",
            trigger_type=TriggerType.IMPLICIT,
            expected_trigger=True,
        )
        result = self._make_result(expected_trigger=True, skill_triggered=False)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        assert analysis.failure_type == "false_negative"
        # "save" and "phrase" are not in the description
        assert "save" in analysis.matching_keywords or "phrase" in analysis.matching_keywords

    def test_no_overlap_detection(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test detection when there's no keyword overlap."""
        test_case = self._make_test_case(
            prompt="Create a log entry for this update",
            trigger_type=TriggerType.IMPLICIT,
            expected_trigger=True,
        )
        result = self._make_result(expected_trigger=True, skill_triggered=False)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        assert analysis.failure_type == "false_negative"
        # Root cause could be no_overlap, missing_keywords, or test_too_indirect
        assert analysis.root_cause in ("no_overlap", "missing_keywords", "test_too_indirect")

    def test_indirect_test_detection(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test detection of overly indirect implicit/contextual tests."""
        test_case = self._make_test_case(
            prompt="I need to record what I did today",
            trigger_type=TriggerType.CONTEXTUAL,
            expected_trigger=True,
        )
        result = self._make_result(expected_trigger=True, skill_triggered=False)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        assert analysis.failure_type == "false_negative"
        # Should flag as likely test bug since test is too indirect
        assert analysis.is_likely_test_bug is True


class TestKeywordExtraction(TestFailureAnalyzer):
    """Tests for keyword extraction functionality."""

    def test_stop_words_filtered(self, analyzer: FailureAnalyzer) -> None:
        """Test that stop words are filtered from keywords."""
        keywords = analyzer._extract_keywords(
            "the quick brown fox jumps over the lazy dog"
        )
        assert "the" not in keywords
        assert "over" not in keywords
        assert "quick" in keywords
        assert "brown" in keywords
        assert "fox" in keywords

    def test_short_words_filtered(self, analyzer: FailureAnalyzer) -> None:
        """Test that very short words are filtered."""
        keywords = analyzer._extract_keywords("I am a go to AI for code")
        assert "am" not in keywords
        assert "go" not in keywords
        assert "code" in keywords


class TestSuggestionGeneration(TestFailureAnalyzer):
    """Tests for fix suggestion generation."""

    def test_suggestions_ordered_by_confidence(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test that suggestions are ordered by confidence (highest first)."""
        test_case = self._make_test_case(
            prompt="Run git commit -m 'fix bug'",
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        assert len(analysis.suggestions) > 0
        # Check ordering
        confidences = [s.confidence for s in analysis.suggestions]
        assert confidences == sorted(confidences, reverse=True)

    def test_suggestions_have_required_fields(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test that all suggestions have required fields."""
        test_case = self._make_test_case(
            prompt="Execute commit command",
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
        for suggestion in analysis.suggestions:
            assert suggestion.category in ("description", "test", "prompt")
            assert suggestion.action in ("update", "add", "remove", "change_expectation")
            assert len(suggestion.description) > 0
            assert 0.0 <= suggestion.confidence <= 1.0


class TestAnalyzerEdgeCases(TestFailureAnalyzer):
    """Tests for edge cases and error handling."""

    def test_passed_test_returns_none(
        self, analyzer: FailureAnalyzer, sample_skill: Skill
    ) -> None:
        """Test that passed tests return None (no analysis needed)."""
        test_case = self._make_test_case(
            prompt="Write a commit message",
            expected_trigger=True,
        )
        result = TriggerResult(
            test_id="test-1",
            test_name="Test case",
            trigger_type=TriggerType.IMPLICIT,
            passed=True,  # Test passed
            skill_triggered=True,
            expected_trigger=True,
            message="Test passed",
        )

        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is None

    def test_skill_without_description(self, analyzer: FailureAnalyzer) -> None:
        """Test handling of skills without description."""
        skill = Skill(
            path=Path("/test/skill"),
            metadata=None,  # No metadata
            body="# Skill\n\nContent.",
            has_scripts=False,
            has_references=False,
            has_assets=False,
        )
        test_case = self._make_test_case(
            prompt="Do something",
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        # Should not raise, should return analysis
        analysis = analyzer.analyze(test_case, result, skill)

        assert analysis is not None
        assert analysis.failure_type == "false_positive"

    def test_empty_prompt(self, analyzer: FailureAnalyzer, sample_skill: Skill) -> None:
        """Test handling of empty prompt."""
        test_case = self._make_test_case(
            prompt="",
            expected_trigger=False,
        )
        result = self._make_result(expected_trigger=False, skill_triggered=True)

        # Should not raise
        analysis = analyzer.analyze(test_case, result, sample_skill)

        assert analysis is not None
