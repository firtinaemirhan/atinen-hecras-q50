"""External files a plan needs, and repairing them inside the working copy.

The delivered data set does not carry its inflow hydrograph inside the model.
``A_A_B_INPINAR.u05`` says::

    Flow Hydrograph= 0
    DSS File=.\\_CBS\\akarcay_debiler\\akarcay_debi.dss
    Use DSS=True

so the boundary condition is read from a DSS file at a path relative to the
project folder.  That path does not resolve: the folder is named ``2_CBS`` on
disk, not ``_CBS``.  HEC-RAS then fails with "Error in Loading Plan Data" and
writes a truncated results file.

Rather than guess, this module states the problem in terms of files: which
paths does the plan reference, which of them are missing, and is the missing
file present elsewhere in the project under the same name?  When it is, the
working copy gets a copy at the location the model expects.  The delivered
data is never touched -- by the time this runs, we are inside the copy.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import ComputeError

_ENCODING = "latin-1"
_DSS_FILE = re.compile(r"^DSS File=(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Reference:
    """A file the model expects to find at a specific relative path."""

    kind: str  # "inflow" or "output"
    declared_in: str  # file name the reference was read from
    raw: str  # exactly as written in the model file
    path: Path  # resolved against the project folder

    @property
    def exists(self) -> bool:
        return self.path.exists()


@dataclass(frozen=True)
class Repair:
    reference: Reference
    action: str
    source: Path | None = None

    def line(self) -> str:
        origin = f" from {self.source}" if self.source else ""
        return f"{self.reference.raw} -> {self.action}{origin}"


def _resolve(project_folder: Path, raw: str) -> Path:
    """Turn a Windows-style relative path from a model file into a real path."""
    return project_folder / raw.replace("\\", "/").lstrip("./")


def _read(path: Path) -> str:
    return path.read_text(encoding=_ENCODING) if path.is_file() else ""


def collect(project_folder: Path, plan_path: Path, flow_file: str) -> list[Reference]:
    """Every DSS file the selected plan depends on.

    The flow file's ``DSS File=`` lines are boundary condition *inputs* and
    must exist before the run. The plan file's is the *output* destination,
    where HEC-RAS writes computed time series; only its folder must exist.
    """
    references: list[Reference] = []

    flow_path = plan_path.with_suffix(f".{flow_file}") if flow_file else None
    if flow_path is not None:
        for raw in _DSS_FILE.findall(_read(flow_path)):
            references.append(
                Reference("inflow", flow_path.name, raw, _resolve(project_folder, raw))
            )

    for raw in _DSS_FILE.findall(_read(plan_path)):
        references.append(
            Reference("output", plan_path.name, raw, _resolve(project_folder, raw))
        )
    return references


def _find_by_name(project_folder: Path, name: str) -> list[Path]:
    return [p for p in project_folder.rglob(name) if p.is_file()]


def repair(project_folder: Path, references: list[Reference]) -> list[Repair]:
    """Make every reference resolve inside ``project_folder``.

    Only ever called on the working copy.  Raises if an input file the model
    needs cannot be found anywhere in the project, because computing without
    the inflow hydrograph would silently produce a meaningless result.
    """
    repairs: list[Repair] = []

    for reference in references:
        if reference.exists:
            continue

        if reference.kind == "output":
            # HEC-RAS writes this file itself; it only needs the folder, so a
            # missing file is normal and only a missing folder is worth acting
            # on -- and worth reporting.
            if reference.path.parent.is_dir():
                continue
            reference.path.parent.mkdir(parents=True, exist_ok=True)
            repairs.append(Repair(reference, "created output folder"))
            continue

        candidates = _find_by_name(project_folder, reference.path.name)
        if not candidates:
            raise ComputeError(
                f"{reference.declared_in} reads its boundary condition from "
                f"{reference.raw}, and no file named {reference.path.name!r} "
                f"exists anywhere in the project.",
                hint="The delivered data set is incomplete; HEC-RAS cannot load "
                "the plan without it.",
            )
        if len(candidates) > 1:
            listed = ", ".join(str(c.relative_to(project_folder)) for c in candidates)
            raise ComputeError(
                f"{reference.raw} is missing and {len(candidates)} files share "
                f"that name: {listed}.",
                hint="Cannot tell which one the model means; fix the path in the "
                "project instead of guessing.",
            )

        source = candidates[0]
        reference.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, reference.path)
        repairs.append(
            Repair(reference, "copied into place", source.relative_to(project_folder))
        )

    return repairs
