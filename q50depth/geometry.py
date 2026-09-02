"""Repair a geometry file whose preprocessed tables were not delivered.

HEC-RAS keeps two kinds of thing in a geometry HDF: the model as drawn, and
the tables its geometry preprocessor derives from that model and the terrain.
The delivered ``A_A_B_INPINAR.g03.hdf`` has the first and not the second::

    Geometry/Structures                       present
    Geometry/GeomPreprocess                   MISSING  <- IBC_CON lives here
    .../Culvert Groups/Barrels/Upstream Cells MISSING
    .../Culvert Groups/Barrels/Downstream Cells MISSING

The unsteady engine reads those structure tables on start-up
(``READ_UN_HDF_STRUC``) and, when they are absent, dies with

    forrtl: severe (157): Program Exception - access violation

instead of reporting them missing.  Re-running the geometry preprocessor does
not help, and the run on 2026-09-02 showed exactly why: it rebuilds the *2D
flow area* tables ("Computing 2D Flow Area 'inpinar' tables complete") and
those are a different thing from the *structure* tables the engine then goes
looking for.  The engine died in the same routine with the mesh tables freshly
built and current.

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
import numpy as np

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
#
# Not "Geometry/Structures/Property Tables". That group was used as the marker
# at first and it is the wrong one: in every file that has it -- the delivered
# results, the other project's geometry -- it is an *empty group*. Its presence
# says nothing, and testing for it made ``--geometry rasprocess`` look like it
# had failed when the question had not been asked properly.
#
# These two are the datasets that carry actual content:
#
# ``Geometry/GeomPreprocess``
#     Output of the geometric preprocessor: IBC_CON (the internal boundary
#     connections), NODE2ICS, Node Info, Reach Connections, Skyline. This is
#     what READ_UN_HDF_STRUC -- "read unsteady HDF structures" -- reads.
#
# ``.../Culvert Groups/Barrels/Upstream Cells`` and ``Downstream Cells``
#     Which 2D mesh cell each culvert barrel opens into, with the station range
#     it covers. The delivered geometry declares two SA/2D connections with
#     four culvert barrels and does not say which cells they connect, so the
#     engine has nothing to resolve them against.
#
# Both are present in the results file from the client's own successful run and
# absent from the delivered geometry.
_BARRELS = "Geometry/Structures/Culvert Groups/Barrels"

REQUIRED = (
    "Geometry/GeomPreprocess",
    f"{_BARRELS}/Upstream Cells",
    f"{_BARRELS}/Downstream Cells",
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


def _required_for(handle: "h5py.File") -> tuple[str, ...]:
    """The subset of :data:`REQUIRED` this particular model needs.

    A model with no culverts never has the barrel-to-cell datasets and is not
    broken for lacking them, so they are only required where the barrels exist.
    """
    return tuple(
        key
        for key in REQUIRED
        if not key.startswith(_BARRELS) or _BARRELS in handle
    )


def missing_tables(geometry_hdf: Path) -> tuple[str, ...]:
    """Which preprocessed groups a geometry HDF lacks."""
    if not geometry_hdf.is_file():
        return REQUIRED
    try:
        with h5py.File(geometry_hdf, "r") as handle:
            return tuple(
                key for key in _required_for(handle) if key not in handle
            )
    except OSError:
        return REQUIRED


def _has_complete_geometry(results_hdf: Path) -> bool:
    try:
        with h5py.File(results_hdf, "r") as handle:
            return all(key in handle for key in _required_for(handle))
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


def complete_with_ras_commander(
    geometry_hdf: Path, rasmap: Path | None, ras_dir: Path
) -> tuple[bool, str]:
    """Run RAS Mapper's geometry-completion pipeline through ras-commander.

    ``RasGeometryCompute.compute_geometry`` is the in-process equivalent of
    RAS Mapper's *Compute Geometry* action.  Its documentation names exactly
    the two things the delivered geometry is missing: "storage-area /
    structure connectivity, and 2D property tables".

    This is not the same thing as ``RasProcess.exe CompleteGeometry``, which
    this module also offers: that one is a subprocess, and on this data set it
    returned without writing either.  Both are kept so the two can be compared
    rather than argued about.

    ``overwrite=True`` matters.  The pipeline skips itself when edge lines
    already exist, and this geometry has them -- so the default would do
    nothing and report success.

    Returns (ran, detail).  ``ran`` is False when ras-commander is not
    installed, which is the normal case off Windows.
    """
    try:
        import ras_commander as rc  # noqa: PLC0415
    except ImportError as exc:
        return False, f"ras-commander is not installed ({exc})"

    try:
        version = _resolve_version(ras_dir)
        outcome = rc.RasGeometryCompute.compute_geometry(
            geom_hdf_path=str(geometry_hdf),
            rasmap_path=str(rasmap) if rasmap is not None else None,
            overwrite=True,
            backup=True,
            hecras_version=version,
        )
    except Exception as exc:  # ras-commander raises its own types
        return True, f"RasGeometryCompute.compute_geometry raised: {exc}"

    parts = [
        f"success={getattr(outcome, 'success', '?')}",
        f"edge_lines={getattr(outcome, 'edge_lines_written', '?')}",
        f"interp_surface={getattr(outcome, 'interpolation_surface_written', '?')}",
        f"{getattr(outcome, 'elapsed_seconds', 0.0):.1f}s",
    ]
    if getattr(outcome, "error", None):
        parts.append(f"error={outcome.error}")
    return True, "RasGeometryCompute.compute_geometry -> " + ", ".join(parts)


def validate_with_ras_commander(
    geometry_hdf: Path, rasmap: Path | None, ras_dir: Path
) -> tuple[bool, str]:
    """Ask HEC-RAS what it thinks is wrong with this geometry.

    RAS Mapper's *Validate Geometry*, run in-process.  Worth doing before a
    run: a geometry the engine cannot start on usually has something to say
    for itself, and reading it beats guessing.
    """
    try:
        import ras_commander as rc  # noqa: PLC0415
    except ImportError as exc:
        return False, f"ras-commander is not installed ({exc})"

    try:
        report = rc.RasGeometryCompute.validate_geometry(
            geom_hdf_path=str(geometry_hdf),
            rasmap_path=str(rasmap) if rasmap is not None else None,
            hecras_version=_resolve_version(ras_dir),
        )
    except Exception as exc:
        return True, f"RasGeometryCompute.validate_geometry raised: {exc}"

    if report is None or len(report) == 0:
        return True, "HEC-RAS geometry validation: no problems reported"
    lines = ["HEC-RAS geometry validation:"]
    for _, row in report.iterrows():
        lines.append(
            f"    [{row.get('severity', '?')}] {row.get('layer', '')} "
            f"{row.get('feature', '')}: {row.get('message', '')}".rstrip()
        )
    return True, "\n".join(lines[:40])


def _resolve_version(ras_dir: Path) -> str:
    """The version string ras-commander identifies a HEC-RAS install by.

    Four separate calls have now been got wrong the same way -- ``ras_version``,
    the terms-and-conditions check, ``RasTcu.status`` and ``hecras_version`` --
    each time by handing over a path where a version was wanted.  The failures
    do not look alike: one reported "not recognized", one silently resolved the
    executable to the bare name ``Ras.exe``, one answered
    "version-unresolved" to a question about a licence, and one said it could
    not find ``RasMapperLib.dll`` in an install where the file plainly is.

    So the conversion lives here and returns one thing: the version, taken from
    the name of the installation folder ("6.6"). A path to ``Ras.exe`` gives the
    name of the folder holding it. A bare version is passed through.
    """
    given = Path(ras_dir).expanduser()
    text = str(ras_dir).strip()
    if re.fullmatch(r"\d+(\.\d+)*", text):
        return text
    if given.suffix.lower() == ".exe":
        return given.parent.name
    return given.name


def _mesh_cells(handle) -> dict[str, np.ndarray]:
    root = handle.get("Geometry/2D Flow Areas")
    if root is None:
        return {}
    return {
        name: node["Cells Center Coordinate"][...]
        for name, node in root.items()
        if isinstance(node, h5py.Group) and "Cells Center Coordinate" in node
    }


def graft_missing(geometry_hdf: Path, results_hdf: Path) -> Repair:
    """Copy only the datasets the geometry lacks, leaving the rest alone.

    :func:`rebuild_from_results` replaces the whole ``Geometry`` group, which
    also throws away the 2D property tables HEC-RAS or RAS Mapper just spent
    time building.  This copies the missing datasets and nothing else.

    That is only safe because the two files number their cells identically.
    Checked on the delivered pair: 5667 cell centres, largest disagreement
    4.7e-09 m, which is float noise.  Their *face* numbering does differ --
    21111 of 25736 entries in ``Faces FacePoint Indexes`` disagree -- so the
    datasets copied here are limited to ones indexed by cell:

        Culvert Groups/Barrels/Upstream Cells    (Cell Index 1553..5397)
        Culvert Groups/Barrels/Downstream Cells  (Cell Index 1515..5454)
        Geometry/GeomPreprocess                  (1D internal-boundary tables,
                                                  a few dozen values about the
                                                  two SA/2D connections)

    The cell numbering is verified again here rather than assumed, and the
    graft is refused if it does not hold.
    """
    missing = missing_tables(geometry_hdf)
    if not missing:
        return Repair(geometry_hdf, results_hdf, ())

    with h5py.File(results_hdf, "r") as source:
        available = tuple(key for key in missing if key in source)
        if not available:
            raise ComputeError(
                f"{results_hdf.name} does not carry {', '.join(missing)} either.",
                hint="There is nothing to copy from.",
            )
        with h5py.File(geometry_hdf, "r") as target:
            theirs, ours = _mesh_cells(source), _mesh_cells(target)
            for name, centres in ours.items():
                other = theirs.get(name)
                if other is None or other.shape != centres.shape:
                    raise ComputeError(
                        f"2D area {name!r} has {len(centres)} cells in "
                        f"{geometry_hdf.name} and "
                        f"{0 if other is None else len(other)} in {results_hdf.name}.",
                        hint="The two files describe different meshes, so cell "
                        "indexes copied from one would point at the wrong cells "
                        "in the other. Refusing to graft.",
                    )
                drift = float(np.abs(centres - other).max())
                if drift > 1e-3:
                    raise ComputeError(
                        f"2D area {name!r} cell centres differ by up to {drift:g} m "
                        f"between {geometry_hdf.name} and {results_hdf.name}.",
                        hint="The cells are not in the same order, so copied cell "
                        "indexes would be wrong. Refusing to graft.",
                    )

    with h5py.File(results_hdf, "r") as source, h5py.File(geometry_hdf, "r+") as target:
        for key in available:
            parent = key.rsplit("/", 1)[0]
            target.require_group(parent)
            if key in target:
                del target[key]
            source.copy(source[key], target[parent], name=key.rsplit("/", 1)[1])
    return Repair(geometry_hdf, results_hdf, available)


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
