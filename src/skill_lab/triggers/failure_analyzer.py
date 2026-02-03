"""Analyze trigger test failures and generate fix suggestions."""

import re

from skill_lab.core.models import (
    FailureAnalysis,
    FixSuggestion,
    Skill,
    TriggerResult,
    TriggerTestCase,
    TriggerType,
)


class FailureAnalyzer:
    """Analyze why trigger tests failed and suggest fixes.

    Uses rule-based heuristics to identify:
    - Why a skill triggered when it shouldn't (false positive)
    - Why a skill didn't trigger when it should (false negative)

    Detection Rules:
    - FP-1: Keyword overlap between prompt and description
    - FP-2: Execution verb without drafting verb
    - FP-3: Inline content provided (e.g., -m 'message')
    - FP-4: Informational query (how do I, what is, etc.)
    - FN-1: Missing keywords in description
    - FN-2: No keyword overlap at all
    - FN-3: Synonym gap (prompt uses synonyms not in description)
    - FN-4: Test too indirect (implicit/contextual with no overlap)
    """

    # Verbs indicating execution (DO something)
    EXECUTION_VERBS = frozenset({
        "run", "execute", "do", "perform", "make", "create",
        "commit", "push", "deploy", "install", "build", "start",
        "stop", "delete", "remove", "update", "apply",
    })

    # Verbs indicating drafting/writing (WRITE something)
    DRAFTING_VERBS = frozenset({
        "write", "draft", "compose", "help", "suggest", "generate",
        "prepare", "create a message", "phrase", "word", "formulate",
    })

    # Patterns indicating informational queries
    INFORMATIONAL_PATTERNS = (
        r"^how (do|can|should|would) (i|we|you)",
        r"^what (is|are|was|were|does|do)",
        r"^why (is|are|does|do|did)",
        r"^explain",
        r"^describe",
        r"^show me",
        r"^list",
        r"^tell me about",
    )

    # Patterns indicating inline content (user provides their own)
    INLINE_CONTENT_PATTERNS = (
        r"-m\s+['\"]",  # git commit -m 'message'
        r"--message\s+['\"]",
        r"-m\s+\S+",  # git commit -m message
    )

    # Common stop words to filter from keyword extraction
    STOP_WORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall",
        "can", "need", "to", "of", "in", "for", "on", "with", "at",
        "by", "from", "as", "into", "through", "during", "before",
        "after", "above", "below", "between", "under", "over", "again",
        "further", "then", "once", "here", "there", "when", "where",
        "why", "how", "all", "each", "every", "both", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "i",
        "you", "he", "she", "it", "we", "they", "me", "him", "her",
        "us", "them", "my", "your", "his", "its", "our", "their",
        "this", "that", "these", "those", "what", "which", "who",
        "whom", "use", "using", "used",
    })

    # Common synonyms mapping
    SYNONYMS = {
        "commit": ["save", "store", "record"],
        "message": ["text", "note", "content"],
        "create": ["make", "generate", "build", "scaffold"],
        "write": ["draft", "compose", "prepare"],
        "fix": ["repair", "resolve", "solve", "debug", "patch"],
        "update": ["modify", "change", "edit", "revise"],
        "delete": ["remove", "drop", "clear"],
        "test": ["spec", "check", "verify", "validate"],
    }

    def analyze(
        self,
        test_case: TriggerTestCase,
        result: TriggerResult,
        skill: Skill,
    ) -> FailureAnalysis | None:
        """Analyze a failed trigger test.

        Args:
            test_case: The test case definition.
            result: The actual test result.
            skill: The parsed skill being tested.

        Returns:
            FailureAnalysis if test failed, None if passed.
        """
        if result.passed:
            return None

        if result.expected_trigger and not result.skill_triggered:
            return self._analyze_false_negative(test_case, skill)
        elif not result.expected_trigger and result.skill_triggered:
            return self._analyze_false_positive(test_case, skill)

        return None

    def _analyze_false_positive(
        self,
        test_case: TriggerTestCase,
        skill: Skill,
    ) -> FailureAnalysis:
        """Analyze why skill triggered when it shouldn't have (FP rules)."""
        prompt_lower = test_case.prompt.lower()
        description = self._get_description(skill).lower()

        # Extract keywords
        prompt_keywords = set(self._extract_keywords(prompt_lower))
        desc_keywords = set(self._extract_keywords(description))
        matching = prompt_keywords & desc_keywords

        suggestions: list[FixSuggestion] = []
        analysis_parts: list[str] = []
        root_cause = "unknown"
        is_test_bug = False

        # FP-1: Keyword overlap
        if matching:
            analysis_parts.append(
                f"Triggered because prompt contains keywords matching "
                f"skill description: {', '.join(sorted(matching)[:5])}"
            )
            root_cause = "keyword_overlap"

        # FP-2: Execution without drafting verb
        has_execution = self._has_verb_type(prompt_lower, self.EXECUTION_VERBS)
        has_drafting = self._has_verb_type(prompt_lower, self.DRAFTING_VERBS)

        if has_execution and not has_drafting:
            analysis_parts.append(
                "However, this prompt asks to EXECUTE an action, "
                "not DRAFT/WRITE content."
            )
            root_cause = "missing_exclusion"

            suggestions.append(FixSuggestion(
                category="description",
                action="add",
                description="Add exclusion clause for execution requests",
                code_snippet="Do NOT use when user asks to execute/run commands.",
                confidence=0.8,
            ))

        # FP-3: Inline content provided
        if self._has_inline_content(prompt_lower):
            analysis_parts.append(
                "The prompt provides inline content (e.g., -m 'message'), "
                "indicating user already has what they need."
            )
            root_cause = "inline_content"

            suggestions.append(FixSuggestion(
                category="description",
                action="add",
                description="Add exclusion for inline content",
                code_snippet="Do NOT use when user provides content inline.",
                confidence=0.85,
            ))

        # FP-4: Informational query
        if self._is_informational_query(prompt_lower):
            analysis_parts.append(
                "This is an informational query (asking ABOUT something), "
                "not a request to use the skill."
            )
            root_cause = "informational_query"

            suggestions.append(FixSuggestion(
                category="description",
                action="add",
                description="Add exclusion for informational questions",
                code_snippet="Do NOT use for questions about how to use tools.",
                confidence=0.75,
            ))

        # Check if this might be a test bug (test expectation is wrong)
        if (
            test_case.trigger_type == TriggerType.NEGATIVE
            and matching
            and (len(matching) >= 2 or (has_execution and has_drafting))
        ):
            is_test_bug = True
            suggestions.append(FixSuggestion(
                category="test",
                action="change_expectation",
                description=(
                    "Consider changing expectation to 'trigger' if "
                    "this prompt genuinely falls within skill scope"
                ),
                confidence=0.5,
            ))

        # Default suggestion if none matched
        if not suggestions:
            suggestions.append(FixSuggestion(
                category="description",
                action="update",
                description="Narrow the skill description to be more specific",
                confidence=0.4,
            ))

        return FailureAnalysis(
            failure_type="false_positive",
            analysis=" ".join(analysis_parts) if analysis_parts else
                     "Skill triggered unexpectedly - description may be too broad",
            root_cause=root_cause,
            matching_keywords=tuple(sorted(matching)[:10]),
            suggestions=tuple(sorted(suggestions, key=lambda s: -s.confidence)),
            is_likely_test_bug=is_test_bug,
        )

    def _analyze_false_negative(
        self,
        test_case: TriggerTestCase,
        skill: Skill,
    ) -> FailureAnalysis:
        """Analyze why skill didn't trigger when it should have (FN rules)."""
        prompt_lower = test_case.prompt.lower()
        description = self._get_description(skill).lower()

        # Extract keywords
        prompt_keywords = set(self._extract_keywords(prompt_lower))
        desc_keywords = set(self._extract_keywords(description))
        matching = prompt_keywords & desc_keywords
        missing_from_desc = prompt_keywords - desc_keywords

        suggestions: list[FixSuggestion] = []
        analysis_parts: list[str] = []
        root_cause = "unknown"
        is_test_bug = False

        # FN-2: No keyword overlap at all
        if not matching:
            analysis_parts.append(
                "No keywords from the skill description appear in the prompt."
            )
            root_cause = "no_overlap"

            # FN-4: Test too indirect
            if test_case.trigger_type in (TriggerType.IMPLICIT, TriggerType.CONTEXTUAL):
                analysis_parts.append(
                    "This implicit/contextual test may be too indirect."
                )
                is_test_bug = True
                root_cause = "test_too_indirect"

                suggestions.append(FixSuggestion(
                    category="test",
                    action="update",
                    description="Make test prompt more explicit about the task",
                    confidence=0.6,
                ))

        # FN-1: Missing keywords
        important_missing = [k for k in missing_from_desc if len(k) > 3][:5]
        if important_missing:
            analysis_parts.append(
                f"Prompt uses words not in description: {', '.join(important_missing)}"
            )
            if root_cause == "unknown":
                root_cause = "missing_keywords"

            suggestions.append(FixSuggestion(
                category="description",
                action="add",
                description="Add missing trigger keywords to description",
                code_snippet=f"Consider adding: {', '.join(important_missing)}",
                confidence=0.7,
            ))

        # FN-3: Synonym gap
        synonym_suggestions = self._find_synonym_gaps(prompt_keywords, description)
        if synonym_suggestions:
            analysis_parts.append(
                "Prompt may use synonyms not in description."
            )
            if root_cause == "unknown":
                root_cause = "synonym_gap"

            suggestions.append(FixSuggestion(
                category="description",
                action="add",
                description="Add synonym phrases that users might use",
                code_snippet=f"Consider adding: {', '.join(synonym_suggestions[:5])}",
                confidence=0.6,
            ))

        # Default suggestion if none matched
        if not suggestions:
            suggestions.append(FixSuggestion(
                category="description",
                action="update",
                description="Broaden the skill description to match user intent",
                confidence=0.4,
            ))

        return FailureAnalysis(
            failure_type="false_negative",
            analysis=" ".join(analysis_parts) if analysis_parts else
                     "Skill did not trigger - description may need broadening",
            root_cause=root_cause,
            matching_keywords=tuple(sorted(missing_from_desc)[:10]),
            suggestions=tuple(sorted(suggestions, key=lambda s: -s.confidence)),
            is_likely_test_bug=is_test_bug,
        )

    def _get_description(self, skill: Skill) -> str:
        """Get the skill description safely."""
        if skill.metadata and skill.metadata.description:
            return skill.metadata.description
        return ""

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract significant keywords from text, filtering stop words."""
        words = re.findall(r"\b[a-z]+\b", text.lower())
        return [w for w in words if w not in self.STOP_WORDS and len(w) > 2]

    def _has_verb_type(self, text: str, verbs: frozenset[str]) -> bool:
        """Check if text contains any verb from the given set."""
        words = set(re.findall(r"\b[a-z]+\b", text.lower()))
        return bool(words & verbs)

    def _has_inline_content(self, text: str) -> bool:
        """Check if text contains inline content patterns."""
        return any(re.search(pattern, text) for pattern in self.INLINE_CONTENT_PATTERNS)

    def _is_informational_query(self, text: str) -> bool:
        """Check if text is an informational query."""
        return any(re.search(pattern, text) for pattern in self.INFORMATIONAL_PATTERNS)

    def _find_synonym_gaps(
        self,
        prompt_keywords: set[str],
        description: str,
    ) -> list[str]:
        """Find synonyms in prompt that are not in description."""
        suggestions = []
        for keyword in prompt_keywords:
            if keyword in self.SYNONYMS:
                for synonym in self.SYNONYMS[keyword]:
                    if synonym not in description and synonym not in suggestions:
                        suggestions.append(synonym)
        return suggestions
