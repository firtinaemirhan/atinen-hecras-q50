"""Application error hierarchy.

Every failure the application can anticipate is raised as a ``Q50Error``.
``main`` catches them, prints a single readable line and exits with the
exception's ``exit_code``.  Anything that escapes as a bare ``Exception`` is a
bug, and is reported as such with a full traceback in the log file.
"""

from __future__ import annotations


class Q50Error(Exception):
    """Base class for expected, user-facing failures."""

    exit_code = 1

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class UsageError(Q50Error):
    """Bad or missing command line input."""

    exit_code = 2


class ProjectError(Q50Error):
    """The HEC-RAS project could not be located, read or understood."""

    exit_code = 3


class ScenarioError(ProjectError):
    """The target scenario could not be resolved to exactly one plan."""

    exit_code = 4


class ComputeError(Q50Error):
    """HEC-RAS could not be started, or the run did not produce results."""

    exit_code = 5


class ResultsError(Q50Error):
    """The results HDF file is missing datasets we depend on."""

    exit_code = 6


class TerrainError(Q50Error):
    """The terrain referenced by the geometry could not be resolved."""

    exit_code = 7


class VerificationError(Q50Error):
    """The produced raster could not be tied back to the selected scenario."""

    exit_code = 8
