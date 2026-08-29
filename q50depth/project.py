"""Locate a HEC-RAS project and resolve a return-period scenario to one plan.

This module never scans the folder for ``*.p0X`` files.  It reads the plan
list out of the project file, because the data set contains a stray
``Backup.p01`` whose title and short identifier are an exact ``Q50`` match.  A
folder scan finds it; the project file does not list it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import ProjectError, ScenarioError

# HEC-RAS writes plain text project/plan files as latin-1 on Windows.
_ENCODING = "latin-1"

# A file is a HEC-RAS project file only if it declares at least one plan.
# The data set also holds bank_lines.prj / akarcay_prj.prj etc., which are
# ESRI coordinate-system files that happen to share the extension.
_PLAN_LINE = re.compile(r"^Plan File=(\S+)\s*$", re.MULTILINE)
_KEY_LINE = re.compile(r"^([^=\n]+)=(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Plan:
    """One entry of the project's plan list."""

    number: str  # "p05"
    path: Path
    title: str
    short_id: str
    geometry_file: str
    flow_file: str
    program_version: str

    @property
    def label(self) -> str:
        return f"{self.number}  title={self.title!r}  short_id={self.short_id!r}"


@dataclass(frozen=True)
class Project:
    """A HEC-RAS project file and the plans it lists."""

    prj_path: Path
    title: str
    current_plan: str | None
    plans: tuple[Plan, ...]

    @property
    def folder(self) -> Path:
        return self.prj_path.parent


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding=_ENCODING)
    except OSError as exc:  # unreadable file, permissions, ...
        raise ProjectError(f"Cannot read {path}: {exc}") from exc


def _parse_keys(text: str) -> dict[str, str]:
    """Collect ``Key=Value`` lines, keeping the first occurrence of each key.

    Values are right-padded with spaces by HEC-RAS (``Short Identifier`` is a
    fixed-width field), so they are stripped here.
    """
    out: dict[str, str] = {}
    for key, value in _KEY_LINE.findall(text):
        key = key.strip()
        if key not in out:
            out[key] = value.strip()
    return out


def find_project_file(root: Path) -> Path:
    """Find the one HEC-RAS project file at or below ``root``.

    ``root`` may be the project folder itself or any parent of it, so the
    caller can point the application at ``CASE_DATA`` without knowing the
    internal layout.
    """
    root = root.expanduser().resolve()
    if not root.exists():
        raise ProjectError(f"Project path does not exist: {root}")

    if root.is_file():
        candidates = [root] if _PLAN_LINE.search(_read_text(root)) else []
    else:
        candidates = [
            p
            for p in sorted(root.rglob("*.prj"))
            if _PLAN_LINE.search(_read_text(p))
        ]

    if not candidates:
        raise ProjectError(
            f"No HEC-RAS project file found under {root}",
            hint="A HEC-RAS .prj file contains 'Plan File=' lines. Coordinate "
            "system .prj files do not; those are ignored on purpose.",
        )
    if len(candidates) > 1:
        listed = "\n  ".join(str(p) for p in candidates)
        raise ProjectError(
            f"{len(candidates)} HEC-RAS project files found under {root}:\n  {listed}",
            hint="Point --project at a single project folder.",
        )
    return candidates[0]


def load_project(prj_path: Path) -> Project:
    """Read the project file and every plan it lists."""
    text = _read_text(prj_path)
    keys = _parse_keys(text)
    numbers = _PLAN_LINE.findall(text)
    if not numbers:
        raise ProjectError(f"{prj_path.name} lists no plans.")

    plans: list[Plan] = []
    missing: list[str] = []
    for number in numbers:
        plan_path = prj_path.with_suffix(f".{number}")
        if not plan_path.is_file():
            missing.append(number)
            continue
        plan_keys = _parse_keys(_read_text(plan_path))
        plans.append(
            Plan(
                number=number,
                path=plan_path,
                title=plan_keys.get("Plan Title", ""),
                short_id=plan_keys.get("Short Identifier", ""),
                geometry_file=plan_keys.get("Geom File", ""),
                flow_file=plan_keys.get("Flow File", ""),
                program_version=plan_keys.get("Program Version", ""),
            )
        )

    if not plans:
        raise ProjectError(
            f"{prj_path.name} lists {len(numbers)} plans but none of the plan "
            f"files exist next to it (missing: {', '.join(missing)}).",
            hint="The project folder looks incomplete.",
        )

    return Project(
        prj_path=prj_path,
        title=keys.get("Proj Title", prj_path.stem),
        current_plan=keys.get("Current Plan"),
        plans=tuple(plans),
    )


def scenario_pattern(scenario: str) -> re.Pattern[str]:
    """Build a boundary-checked pattern for a return-period label.

    ``Q50`` must not match ``Q500`` or ``Q1000``.  Plain substring search does:
    ``"Q50" in "INPINAR_Q500_UNSTEADY"`` is ``True``.  The lookarounds forbid a
    digit on either side, and ``0*`` accepts a zero-padded spelling (``Q050``).
    """
    match = re.fullmatch(r"[Qq](\d+)", scenario.strip())
    if not match:
        raise ScenarioError(
            f"Scenario must look like 'Q50', got {scenario!r}.",
        )
    digits = match.group(1).lstrip("0") or "0"
    return re.compile(rf"(?<![0-9])[Qq]0*{digits}(?![0-9])")


def select_plan(project: Project, scenario: str) -> tuple[Plan, dict[str, list[str]]]:
    """Return the single plan matching ``scenario``, plus the match evidence.

    The plan number is never assumed.  Both the human-readable ``Plan Title``
    and the ``Short Identifier`` are tested, and the caller gets the field that
    matched so it can be written into the run log.
    """
    pattern = scenario_pattern(scenario)
    matches: list[Plan] = []
    evidence: dict[str, list[str]] = {}

    for plan in project.plans:
        hits = [
            name
            for name, value in (("Plan Title", plan.title), ("Short Identifier", plan.short_id))
            if pattern.search(value)
        ]
        if hits:
            matches.append(plan)
            evidence[plan.number] = hits

    if not matches:
        listed = "\n  ".join(p.label for p in project.plans)
        raise ScenarioError(
            f"No plan in {project.prj_path.name} matches scenario {scenario}.",
            hint=f"Plans listed by the project:\n  {listed}",
        )
    if len(matches) > 1:
        listed = "\n  ".join(p.label for p in matches)
        raise ScenarioError(
            f"Scenario {scenario} matches {len(matches)} plans, which is ambiguous:\n  {listed}",
            hint="Refine --scenario, or fix the plan titles in the project.",
        )
    return matches[0], evidence
