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

from dataclasses import dataclass
from pathlib import Path

import h5py

from .errors import ComputeError

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
