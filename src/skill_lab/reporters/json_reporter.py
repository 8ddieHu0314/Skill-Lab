"""JSON reporter for evaluation results."""

import json
from pathlib import Path
from typing import Any, TextIO

from skill_lab.core.models import EvaluationReport

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

    def format(self, report: EvaluationReport) -> str:
        """Format an evaluation report as JSON.

        Args:
            report: The evaluation report to format.

        Returns:
            JSON string representation.
        """
        data: dict[str, Any] = report.to_dict()
        if self.include_schema_version:
            data = {"schema_version": SCHEMA_VERSION, **data}
        return json.dumps(data, indent=self.indent)

    def write(self, report: EvaluationReport, output: TextIO) -> None:
        """Write an evaluation report to a file-like object.

        Args:
            report: The evaluation report to write.
            output: File-like object to write to.
        """
        output.write(self.format(report))
        output.write("\n")

    def write_file(self, report: EvaluationReport, path: str | Path) -> None:
        """Write an evaluation report to a file.

        Args:
            report: The evaluation report to write.
            path: Path to the output file.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            self.write(report, f)
