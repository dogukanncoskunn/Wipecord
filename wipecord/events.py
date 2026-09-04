"""Messages passed from the worker thread to the UI.

Tkinter is not thread-safe: touching a widget from the worker crashes at
random. The worker therefore only ever puts these frozen dataclasses on a
queue, and the UI thread drains that queue on its own timer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Level(str, Enum):
    """Log severity, which the UI maps to colours."""

    INFO = "info"
    SUCCESS = "success"
    WARN = "warn"
    ERROR = "error"
    WAIT = "wait"
    DELETE = "delete"


class State(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    PREVIEW = "preview"
    DELETING = "deleting"
    PAUSED = "paused"
    DONE = "done"


@dataclass(frozen=True)
class LogEvent:
    level: Level
    text: str


@dataclass(frozen=True)
class StateEvent:
    state: State


@dataclass(frozen=True)
class ProgressEvent:
    done: int
    total: int
    elapsed: float = 0.0
    eta: float | None = None


@dataclass(frozen=True)
class PreviewEvent:
    """The result of a scan: exactly what a delete run would remove."""

    messages: tuple = field(default_factory=tuple)
    channel_label: str = ""


@dataclass(frozen=True)
class Summary:
    scanned: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0
    duration: float = 0.0
    dry_run: bool = False
    stopped: bool = False
    error: str | None = None


@dataclass(frozen=True)
class DoneEvent:
    summary: Summary
