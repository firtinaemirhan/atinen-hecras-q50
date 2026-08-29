"""Repair a geometry file whose preprocessed tables were not delivered.

HEC-RAS keeps two kinds of thing in a geometry HDF: the model as drawn, and
the tables its geometry preprocessor derives from that model and the terrain.
The delivered ``A_A_B_INPINAR.g03.hdf`` has the first and not the second::

    Geometry/Structures                  present
    Geometry/Structures/Property Tables  MISSING
    Geometry/GeomPreprocess              MISSING
    Geometry/Cross Sections              MISSING

The unsteady engine reads those structure tables on start-up
(``READ_UN_HDF_STRUC``) and, when they are absent, dies with

    forrtl: severe (157): Program Exception - access violation

instead of reporting them missing.  Re-running the geometry preprocessor does
not help: it rebuilds the 2D flow area tables ("Computing 2D Flow Area
'inpinar' tables") and leaves the structure tables alone.

The tables do exist in the delivery, inside the results file the original run
produced.  That file carries a complete ``Geometry`` group for this same
geometry and terrain, so the working copy's geometry HDF is rebuilt from it.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import h5py

from .errors import ComputeError

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
        start=1,
    )
}
_TERRAIN_DATE = re.compile(r"^(\d{2})([A-Za-z]{3})(\d{4})\s+(\d{2}):(\d{2}):(\d{2})$")

# What a geometry the unsteady engine can start on must contain.
REQUIRED = (
    "Geometry/Structures/Property Tables",
    "Geometry/GeomPreprocess",
)


@dataclass(frozen=True)
class Repair:
    geometry_hdf: Path
    source: Path
    added: tuple[str, ...]

    def line(self) -> str:
        return (
            f"{self.geometry_hdf.name} rebuilt from {self.source.name} "
            f"(added {', '.join(self.added)})"
        )


def _decode(value: object) -> str:
    return value.decode("latin-1").strip() if isinstance(value, bytes) else str(value).strip()


def align_terrain_timestamp(geometry_hdf: Path, project_folder: Path) -> str | None:
    """Make the terrain file look as old as the geometry says it is.

    A geometry records ``Terrain File Date``, and HEC-RAS compares it with the
    terrain file's own modification time.  Copying a project preserves those
    times, but a different machine reads them in a different time zone, and
    HEC-RAS then reports

        Computing 2D Flow Area tables: Associated terrain has been updated.

    and rebuilds the tables -- discarding the structure tables again.  Setting
    the terrain file's timestamp to the recorded one removes the disagreement.
    Only the working copy is touched.

    Returns the timestamp that was applied, or None if there was nothing to do.
    """
    try:
        with h5py.File(geometry_hdf, "r") as handle:
            geometry = handle.get("Geometry")
            if geometry is None:
                return None
            recorded = _decode(geometry.attrs.get("Terrain File Date", b""))
            relative = _decode(geometry.attrs.get("Terrain Filename", b""))
    except OSError:
        return None

    match = _TERRAIN_DATE.match(recorded)
    if not match or not relative:
        return None
    day, month, year, hour, minute, second = match.groups()
    if month.upper() not in _MONTHS:
        return None
    stamp = datetime(
        int(year), _MONTHS[month.upper()], int(day), int(hour), int(minute), int(second)
    ).timestamp()

    terrain = (project_folder / relative.replace("\\", "/").lstrip("./")).resolve()
    touched = []
    for path in (terrain, *terrain.parent.glob(terrain.stem + ".*")):
        if path.is_file():
            os.utime(path, (stamp, stamp))
            touched.append(path)
    return recorded if touched else None


def missing_tables(geometry_hdf: Path) -> tuple[str, ...]:
    """Which preprocessed groups a geometry HDF lacks."""
    if not geometry_hdf.is_file():
        return REQUIRED
    try:
        with h5py.File(geometry_hdf, "r") as handle:
            return tuple(key for key in REQUIRED if key not in handle)
    except OSError:
        return REQUIRED


def _has_complete_geometry(results_hdf: Path) -> bool:
    try:
        with h5py.File(results_hdf, "r") as handle:
            return all(key in handle for key in REQUIRED)
    except OSError:
        return False


def complete_with_hecras(
    geometry_hdf: Path, rasmap: Path | None, ras_dir: Path, timeout: int = 1800
) -> tuple[bool, str]:
    """Ask HEC-RAS's own tool to derive the missing tables.

    ``RasProcess.exe CompleteGeometry`` is the GUI-free equivalent of
    RASMapper's *Compute Geometry*: it writes storage-area and structure
    connectivity and the 2D property tables, stamped with the source-data
    hashes HEC-RAS checks, so a later run treats them as current instead of
    rebuilding them.  This is the right way to obtain the tables -- the
    delivery simply does not include them.

    The command line is the one ras-commander issues; its own success flag is
    not trusted here because it also requires 1D river edge lines, which a 2D
    model does not have.  What counts is whether the tables are there
    afterwards, and the caller checks that.

    Returns (ran, detail).  ``ran`` is False when the tool is not installed.
    """
    executable = Path(ras_dir).expanduser()
    if executable.is_file() and executable.suffix.lower() == ".exe":
        executable = executable.parent
    executable = executable / "RasProcess.exe"
    if not executable.is_file():
        return False, f"{executable.name} is not in {executable.parent}"

    arguments = [str(executable), "CompleteGeometry", str(geometry_hdf)]
    if rasmap is not None and rasmap.is_file():
        arguments.append(f"RasMapFilename={rasmap}")

    try:
        finished = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(geometry_hdf.parent),
        )
    except subprocess.TimeoutExpired:
        return True, f"RasProcess.exe timed out after {timeout} s"
    except OSError as exc:
        return False, f"RasProcess.exe could not be started: {exc}"

    output = " ".join((finished.stdout or "").split())[-300:]
    return True, f"RasProcess.exe CompleteGeometry -> rc={finished.returncode} {output}".strip()


def rebuild_from_results(geometry_hdf: Path, results_hdf: Path) -> Repair:
    """Replace ``geometry_hdf``'s Geometry group with the one in ``results_hdf``.

    The geometry file's own root attributes are kept, so the result is still a
    HEC-RAS geometry file and not a copy of a results file.
    """
    missing = missing_tables(geometry_hdf)
    if not _has_complete_geometry(results_hdf):
        raise ComputeError(
            f"{results_hdf.name} does not carry a complete geometry either, so the "
            f"preprocessed tables missing from {geometry_hdf.name} cannot be recovered.",
            hint="The unsteady engine needs Structures/Property Tables and will "
            "crash without them.",
        )

    root_attributes: dict[str, object] = {}
    if geometry_hdf.is_file():
        with h5py.File(geometry_hdf, "r") as handle:
            root_attributes = dict(handle.attrs)

    temporary = geometry_hdf.with_suffix(geometry_hdf.suffix + ".rebuilt")
    with h5py.File(results_hdf, "r") as source, h5py.File(temporary, "w") as target:
        for key, value in root_attributes.items():
            target.attrs[key] = value
        target.attrs.setdefault("File Type", b"HEC-RAS Geometry")
        source.copy("Geometry", target, name="Geometry")

    temporary.replace(geometry_hdf)
    return Repair(geometry_hdf, results_hdf, missing)
