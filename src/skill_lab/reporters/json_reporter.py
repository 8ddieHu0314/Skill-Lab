"""JSON reporter for evaluation results."""

import json
from pathlib import Path
from typing import TextIO

from skill_lab.core.models import EvaluationReport


class JsonReporter:
    """Reporter that outputs evaluation results as JSON."""

    def __init__(self, indent: int = 2) -> None:
        """Initialize the reporter.

        Args:
            indent: JSON indentation level. Use None for compact output.
        """
        self.indent = indent

    def format(self, report: EvaluationReport) -> str:
        """Format an evaluation report as JSON.

        Args:
            report: The evaluation report to format.

        Returns:
            JSON string representation.
        """
        return json.dumps(report.to_dict(), indent=self.indent)

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
