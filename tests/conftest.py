"""Test doubles. No test in this suite touches the network."""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import pytest


def _pin_tcl_paths() -> None:
    """Point Tk at the base interpreter's tcl/tk libraries.

    Inside a venv these variables are unset, and Tk only bootstraps its search
    path successfully once. The second root created in a process then fails
    with "Can't find a usable tk.tcl", which would silently skip the UI tests.
    """
    tcl_root = Path(sys.base_prefix) / "tcl"
    for variable, folder in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
        if os.environ.get(variable):
            continue
        candidate = tcl_root / folder
        if candidate.is_dir():
            os.environ[variable] = str(candidate)


_pin_tcl_paths()


class FakeResponse:
    def __init__(self, status: int, data=None, headers=None, *, body_is_json=True):
        self.status_code = status
        self._data = data
        self._body_is_json = body_is_json
        self.headers = headers or {}
        self.content = b"{}" if data is not None else b""

    def json(self):
        if not self._body_is_json or self._data is None:
            raise ValueError("no json")
        return self._data


class FakeSession:
    """Replays a scripted list of responses; raises any Exception it is given."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict | None]] = []
        self.headers: dict[str, str] = {}

    def request(self, method, url, params=None, timeout=None):
        self.calls.append((method, url, params))
        if not self.responses:
            raise AssertionError(f"unexpected extra request: {method} {url}")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


class FakeSleeper:
    """Records sleeps instead of performing them.

    `stop_at` makes the Nth sleep report a stop, which is how the tests exercise
    interruption without real timing.
    """

    def __init__(self, stop_at: int | None = None):
        self.slept: list[float] = []
        self.stop_at = stop_at

    def sleep(self, seconds: float) -> bool:
        self.slept.append(seconds)
        if self.stop_at is not None and len(self.slept) >= self.stop_at:
            return False
        return True

    @property
    def total(self) -> float:
        return sum(self.slept)


@pytest.fixture
def sleeper():
    return FakeSleeper()


@pytest.fixture
def rng():
    # Seeded so jitter is deterministic across runs.
    return random.Random(1234)
