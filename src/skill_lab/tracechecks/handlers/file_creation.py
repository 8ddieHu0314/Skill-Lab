"""Handler for file_creation trace checks."""

from pathlib import Path

from skill_lab.core.models import TraceCheckDefinition, TraceCheckResult
from skill_lab.tracechecks.handlers.base import TraceCheckHandler
from skill_lab.tracechecks.registry import register_trace_handler
from skill_lab.triggers.trace_analyzer import TraceAnalyzer


@register_trace_handler("file_creation")
class FileCreationHandler(TraceCheckHandler):
    """Check if a file exists at the specified path.

    YAML format:
        - id: package-json-created
          type: file_creation
          path: "package.json"
    """

    def run(
        self,
        check: TraceCheckDefinition,
        analyzer: TraceAnalyzer,
        project_dir: Path,
    ) -> TraceCheckResult:
        """Check if a file was created at the specified path.

        Args:
            check: Check definition with path field.
            analyzer: TraceAnalyzer (used for file_was_created method).
            project_dir: Project directory for path resolution.

        Returns:
            TraceCheckResult indicating if file exists.
        """
        file_path = self._require_field(check, "path")
        if isinstance(file_path, TraceCheckResult):
            return file_path

        if analyzer.file_was_created(file_path, project_dir):
            return self._pass(
                check,
                f"File '{file_path}' exists",
                {"path": file_path, "full_path": str(project_dir / file_path)},
            )
        else:
            return self._fail(
                check,
                f"File '{file_path}' was not created",
                {"path": file_path, "full_path": str(project_dir / file_path)},
            )
