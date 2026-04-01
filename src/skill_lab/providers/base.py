"""Abstract base class for execution providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from skill_lab.runtimes.base import RuntimeAdapter


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable context for a single test execution.

    Created by the provider's prepare_test() method and passed through
    the execute/collect/cleanup lifecycle.
    """

    skill_path: Path
    """Original skill directory on the host."""

    skill_name: str
    """Skill name (used for discovery path construction)."""

    working_dir: Path
    """Isolated directory where the agent runs."""

    trace_path: Path
    """Where trace output is written."""


class ExecutionProvider(ABC):
    """Abstract base for execution environment providers.

    Providers manage the lifecycle of isolated environments for trigger
    test execution. The lifecycle is:

        setup()          — one-time setup before all tests
        prepare_test()   — create isolated environment per test
        execute()        — run the agent in the environment
        collect_trace()  — copy trace from environment to host
        cleanup_test()   — tear down per-test environment
        teardown()       — final cleanup after all tests

    Implementations:
        - LocalProvider: temp directory isolation (default, zero dependencies)
        - DockerProvider: container isolation (opt-in, requires Docker)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name (e.g., 'local', 'docker')."""
        ...

    def setup(self, skill_path: Path, skill_name: str) -> None:  # noqa: B027
        """One-time setup before all tests.

        Override for providers that need pre-work (e.g., building Docker images).
        Default is a no-op.

        Args:
            skill_path: Path to the skill directory.
            skill_name: Name of the skill being tested.
        """

    @abstractmethod
    def prepare_test(
        self,
        skill_path: Path,
        skill_name: str,
        trace_path: Path,
    ) -> ExecutionContext:
        """Create an isolated environment for a single test.

        Args:
            skill_path: Path to the skill directory on the host.
            skill_name: Name of the skill (for discovery path construction).
            trace_path: Where to write the execution trace.

        Returns:
            ExecutionContext with the isolated working directory.
        """
        ...

    @abstractmethod
    def execute(
        self,
        context: ExecutionContext,
        runtime: RuntimeAdapter,
        prompt: str,
        stop_on_skill: str | None,
    ) -> int:
        """Run the agent in the prepared environment.

        Args:
            context: Execution context from prepare_test().
            runtime: Runtime adapter for the agent CLI.
            prompt: User prompt to send to the agent.
            stop_on_skill: If set, terminate early when this skill is triggered.

        Returns:
            Exit code from the agent process.
        """
        ...

    def collect_trace(self, context: ExecutionContext) -> Path:
        """Copy trace file from the execution environment to the host.

        Override for providers where the trace is written inside an isolated
        environment (e.g., Docker). Default returns the trace path as-is.

        Args:
            context: Execution context with trace path.

        Returns:
            Path to the trace file on the host.
        """
        return context.trace_path

    @abstractmethod
    def cleanup_test(self, context: ExecutionContext) -> None:
        """Tear down the per-test environment.

        Called in a finally block after each test. Must be idempotent.

        Args:
            context: Execution context to clean up.
        """
        ...

    def teardown(self) -> None:  # noqa: B027
        """Final cleanup after all tests.

        Override for providers that need post-work (e.g., removing Docker images).
        Default is a no-op.
        """
