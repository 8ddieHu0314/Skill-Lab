"""JSON reporter for evaluation results."""

import json
from pathlib import Path
from typing import Any, TextIO

from skill_lab.core.llm import GenerationUsage
from skill_lab.core.models import EvaluationReport, JudgeResult

# Schema version for API compatibility tracking
SCHEMA_VERSION = "1.0"


class JsonReporter:
    """Reporter that outputs evaluation results as JSON."""

    def __init__(self, indent: int = 2, include_schema_version: bool = True) -> None:
        """Initialize the reporter.

        Args:
            indent: JSON indentation level. Use None for compact output.
            include_schema_version: If True, add schema_version field to output.
        """
        self.indent = indent
        self.include_schema_version = include_schema_version

    def format(
        self,
        report: EvaluationReport,
        judge_result: JudgeResult | None = None,
        judge_usage: GenerationUsage | None = None,
    ) -> str:
        """Format an evaluation report as JSON.

        Args:
            report: The evaluation report to format.
            judge_result: Optional LLM judge result to include.
            judge_usage: Optional token usage from the judge call.

        Returns:
            JSON string representation.
        """
        data: dict[str, Any] = report.to_dict()
        if self.include_schema_version:
            data = {"schema_version": SCHEMA_VERSION, **data}

        if judge_result is not None:
            review_data = judge_result.to_dict()
            if judge_usage is not None:
                review_data["usage"] = {
                    "input_tokens": judge_usage.input_tokens,
                    "output_tokens": judge_usage.output_tokens,
                    "total_tokens": judge_usage.total_tokens,
                    "cost": (
                        round(judge_usage.total_cost, 6) if judge_usage.has_pricing else None
                    ),
                }
            data["judge_review"] = review_data
        else:
            data["judge_review"] = None

        return json.dumps(data, indent=self.indent)

    def write(
        self,
        report: EvaluationReport,
        output: TextIO,
        judge_result: JudgeResult | None = None,
        judge_usage: GenerationUsage | None = None,
    ) -> None:
        """Write an evaluation report to a file-like object.

        Args:
            report: The evaluation report to write.
            output: File-like object to write to.
            judge_result: Optional LLM judge result to include.
            judge_usage: Optional token usage from the judge call.
        """
        output.write(self.format(report, judge_result=judge_result, judge_usage=judge_usage))
        output.write("\n")

    def write_file(
        self,
        report: EvaluationReport,
        path: str | Path,
        judge_result: JudgeResult | None = None,
        judge_usage: GenerationUsage | None = None,
    ) -> None:
        """Write an evaluation report to a file.

        Args:
            report: The evaluation report to write.
            path: Path to the output file.
            judge_result: Optional LLM judge result to include.
            judge_usage: Optional token usage from the judge call.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            self.write(report, f, judge_result=judge_result, judge_usage=judge_usage)
