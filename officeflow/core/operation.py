"""The Operation contract: the single interface every automation tool implements.

An operation is GUI-agnostic. It declares its parameters as data (``Param``) so
that any front end (the desktop GUI, the workflow engine, a test) can drive it
without knowing anything about its internals.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, ClassVar, Mapping, Sequence

from officeflow.services.files import unique_path

ProgressCallback = Callable[[int, int, str], None]


class OperationError(Exception):
    """A problem the user can understand and fix (bad parameter, bad input)."""


class Cancelled(Exception):
    """Raised inside an operation when the user cancels it."""


class ParamType(str, Enum):
    TEXT = "text"
    MULTILINE = "multiline"
    INT = "int"
    BOOL = "bool"
    CHOICE = "choice"
    FILE = "file"


@dataclass(frozen=True)
class Param:
    """Declarative description of one user-configurable setting."""

    key: str
    label: str
    type: ParamType = ParamType.TEXT
    default: Any = ""
    help: str = ""
    choices: tuple[tuple[str, str], ...] = ()  # (value, label)
    required: bool = False
    minimum: int = 0
    maximum: int = 1_000_000
    placeholder: str = ""

    def coerce(self, value: Any) -> Any:
        if value is None:
            value = self.default
        if self.type is ParamType.BOOL:
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)
        if self.type is ParamType.INT:
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise OperationError(f"“{self.label}” must be a whole number.") from None
            if not self.minimum <= number <= self.maximum:
                raise OperationError(
                    f"“{self.label}” must be between {self.minimum} and {self.maximum}."
                )
            return number
        if self.type is ParamType.CHOICE:
            allowed = [c[0] for c in self.choices]
            if value not in allowed:
                raise OperationError(f"“{self.label}” has an invalid value: {value!r}.")
            return value
        text = str(value)
        if self.type is not ParamType.MULTILINE:
            text = text.strip()
        if self.required and not text.strip():
            raise OperationError(f"“{self.label}” is required.")
        return text


@dataclass
class Preview:
    """What an operation *would* do. Building a preview never modifies files."""

    summary: str
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class OperationResult:
    """What an operation did.

    ``outputs`` are the primary files produced (they feed the next workflow
    step); ``reports`` are side files such as logs or summaries.
    """

    summary: str
    outputs: list[Path] = field(default_factory=list)
    reports: list[Path] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class OperationContext:
    """Everything an operation needs from its host: where to write, how to
    report progress, and whether to stop."""

    def __init__(
        self,
        output_dir: Path,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self._progress = progress
        self.cancel_event = cancel_event or threading.Event()
        self.log = logger or logging.getLogger("officeflow.operation")
        self._taken: set[Path] = set()

    def progress(self, done: int, total: int, message: str = "") -> None:
        self.check_cancelled()
        if self._progress:
            self._progress(done, total, message)
            self.check_cancelled()

    def check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def out_path(self, name: str | Path) -> Path:
        """Reserve a path inside the output folder that never overwrites an
        existing file (``report.xlsx`` → ``report (2).xlsx``)."""
        target = self.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        return unique_path(target, self._taken)

    def release(self, path: Path) -> None:
        """Give back a reserved path that ended up not being written."""
        self._taken.discard(path)

    def child(self, subdir: str, progress: ProgressCallback | None = None) -> "OperationContext":
        return OperationContext(self.output_dir / subdir, progress, self.cancel_event, self.log)


class Operation(ABC):
    """Base class for all automation tools (built-in and plugins)."""

    id: ClassVar[str]
    name: ClassVar[str]
    category: ClassVar[str]  # "excel" | "pdf" | "word" | "cross"
    description: ClassVar[str] = ""
    input_extensions: ClassVar[tuple[str, ...]] = ()
    output_extensions: ClassVar[tuple[str, ...]] = ()  # what ``outputs`` contains (workflow chaining)
    input_label: ClassVar[str] = "Files or folders"
    min_inputs: ClassVar[int] = 1
    max_inputs: ClassVar[int | None] = None
    params: ClassVar[tuple[Param, ...]] = ()

    def clean_params(self, raw: Mapping[str, Any] | None) -> dict[str, Any]:
        raw = dict(raw or {})
        return {p.key: p.coerce(raw.get(p.key)) for p in self.params}

    def check_inputs(self, inputs: Sequence[Path]) -> None:
        kinds = ", ".join(self.input_extensions) or "files"
        if len(inputs) < self.min_inputs:
            need = "one file" if self.min_inputs == 1 else f"{self.min_inputs} files"
            raise OperationError(
                f"{self.name} needs at least {need} ({kinds}); {len(inputs)} found."
            )
        if self.max_inputs is not None and len(inputs) > self.max_inputs:
            raise OperationError(
                f"{self.name} accepts at most {self.max_inputs} files; {len(inputs)} given."
            )

    def preview(
        self, inputs: Sequence[Path], params: dict[str, Any], ctx: OperationContext
    ) -> Preview:
        """Default preview: list the files that will be processed."""
        return Preview(
            summary=f"{len(inputs)} file(s) will be processed. Originals are never modified.",
            headers=["File", "Folder"],
            rows=[[p.name, str(p.parent)] for p in inputs],
        )

    @abstractmethod
    def run(
        self, inputs: Sequence[Path], params: dict[str, Any], ctx: OperationContext
    ) -> OperationResult:
        ...
