"""Reader for a HEC-RAS plan results (HDF5) file.

The file is self-describing: it carries the projection WKT, the identity of
the plan that produced it, the terrain the geometry was built on, and the 2D
mesh itself.  Everything the raster needs is read from here, so nothing about
this particular data set has to be hard coded.

Note on the depth: HEC-RAS does not store a maximum-depth dataset.  Summary
output holds ``Maximum Water Surface`` (a water surface *elevation* per cell).
Depth is derived later, against the terrain, in :mod:`q50depth.depth`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from .errors import ResultsError

_SUMMARY = (
    "Results/Unsteady/Output/Output Blocks/Base Output/"
    "Summary Output/2D Flow Areas"
)
_MESH_ROOT = "Geometry/2D Flow Areas"
_MAX_WS = "Maximum Water Surface"


def _attr(node, name: str, default: str | None = None) -> str | None:
    value = node.attrs.get(name, default)
    if isinstance(value, bytes):
        return value.decode("latin-1").strip()
    if isinstance(value, np.ndarray) and value.size == 1:
        value = value.reshape(-1)[0]
        if isinstance(value, bytes):
            return value.decode("latin-1").strip()
    return None if value is None else str(value).strip()


@dataclass(frozen=True)
class Mesh:
    """One 2D flow area, with the maximum water surface reached in each cell."""

    name: str
    face_point_xy: np.ndarray  # (n_face_points, 2) float64
    cell_face_points: np.ndarray  # (n_cells, max_vertices) int32, -1 padded
    cell_center_xy: np.ndarray  # (n_cells, 2) float64
    cell_min_elevation: np.ndarray  # (n_cells,) float32, NaN for ghost cells
    max_water_surface: np.ndarray  # (n_cells,) float32, metres
    max_ws_time_days: np.ndarray  # (n_cells,) float32, days from run start
    # (n_cells,) float32 -- the wetted ground area inside the cell, which is
    # not the area of the cell polygon: it follows the sub-grid terrain. Used
    # to weight cells when the sloping water surface is averaged at a corner
    # they share. Optional: HEC-RAS writes it, a hand-built mesh need not.
    cell_surface_area: np.ndarray | None = None

    @property
    def cell_count(self) -> int:
        return int(self.cell_center_xy.shape[0])

    @property
    def real_cells(self) -> np.ndarray:
        """Cells that are actual polygons.

        HEC-RAS pads the cell arrays with boundary "ghost" cells that carry
        fewer than three face points and a NaN minimum elevation.
        """
        enough_vertices = (self.cell_face_points >= 0).sum(axis=1) >= 3
        return enough_vertices & np.isfinite(self.cell_min_elevation)

    def wet_cells(self, tolerance_m: float = 0.0) -> np.ndarray:
        """Cells whose maximum water surface rose above their own bed.

        A cell that never got wet is reported by HEC-RAS with a maximum water
        surface equal to its minimum elevation.  Those cells must be dropped
        before rasterising: where the bed sits on a raised terrain
        modification (a building) and the surrounding ground does not, keeping
        them paints the modification height as water depth.
        """
        return self.real_cells & (
            self.max_water_surface > self.cell_min_elevation + tolerance_m
        )


@dataclass(frozen=True)
class PlanResults:
    """Everything read out of one plan HDF file."""

    hdf_path: Path
    projection_wkt: str
    plan_title: str
    plan_short_id: str
    plan_filename: str
    geometry_filename: str
    geometry_title: str
    flow_filename: str
    flow_title: str
    program_version: str
    simulation_window: str
    terrain_filename: str
    terrain_layer: str
    meshes: tuple[Mesh, ...]


def results_path_for(plan_path: Path) -> Path:
    """``.../A_A_B_INPINAR.p05`` -> ``.../A_A_B_INPINAR.p05.hdf``."""
    return plan_path.with_name(plan_path.name + ".hdf")


def _read_mesh(handle: h5py.File, name: str) -> Mesh:
    geom = handle[f"{_MESH_ROOT}/{name}"]
    summary_key = f"{_SUMMARY}/{name}/{_MAX_WS}"
    if summary_key not in handle:
        raise ResultsError(
            f"2D area {name!r} has no '{_MAX_WS}' summary output.",
            hint="The plan was not computed, or was computed without summary output.",
        )
    required = (
        "FacePoints Coordinate",
        "Cells FacePoint Indexes",
        "Cells Center Coordinate",
        "Cells Minimum Elevation",
    )
    for key in required:
        if key not in geom:
            raise ResultsError(f"2D area {name!r} is missing geometry dataset {key!r}.")

    max_ws = handle[summary_key]
    rows = [
        r.decode("latin-1").strip() if isinstance(r, bytes) else str(r)
        for r in max_ws.attrs.get("Rows Variables", [b"WSEL", b"Time"])
    ]
    if max_ws.ndim != 2 or "WSEL" not in rows:
        raise ResultsError(
            f"Unexpected layout for '{_MAX_WS}' in {name!r}: "
            f"shape={max_ws.shape}, rows={rows}."
        )
    wsel_row = rows.index("WSEL")
    time_row = rows.index("Time") if "Time" in rows else None
    data = max_ws[...]

    return Mesh(
        name=name,
        face_point_xy=geom["FacePoints Coordinate"][...],
        cell_face_points=geom["Cells FacePoint Indexes"][...],
        cell_center_xy=geom["Cells Center Coordinate"][...],
        cell_min_elevation=geom["Cells Minimum Elevation"][...],
        max_water_surface=data[wsel_row],
        max_ws_time_days=(
            data[time_row] if time_row is not None else np.zeros_like(data[wsel_row])
        ),
        cell_surface_area=(
            geom["Cells Surface Area"][...] if "Cells Surface Area" in geom else None
        ),
    )


def load(hdf_path: Path) -> PlanResults:
    """Open a plan HDF file and read geometry, results and provenance."""
    if not hdf_path.is_file():
        raise ResultsError(
            f"No results file at {hdf_path}",
            hint="The plan has not been computed yet. Run without "
            "--use-existing-results to let HEC-RAS produce it.",
        )
    try:
        handle = h5py.File(hdf_path, "r")
    except OSError as exc:
        raise ResultsError(f"{hdf_path.name} is not a readable HDF5 file: {exc}") from exc

    with handle:
        file_type = _attr(handle, "File Type") or ""
        if not file_type or "Plan Data" not in handle:
            # HEC-RAS creates the results file at the start of a run and fills
            # it in as it goes. A file with no type or no plan block is one
            # that was abandoned mid-run.
            raise ResultsError(
                f"{hdf_path.name} is a partial results file: the run started but "
                f"did not finish.",
                hint=f"HEC-RAS wrote it and stopped. Its own log, "
                f"{hdf_path.stem.rsplit('.', 1)[0]}.bco* in the same folder, says why; "
                "a broken file reference or a dialog during loading is the usual cause.",
            )
        if "Results" not in file_type:
            raise ResultsError(
                f"{hdf_path.name} is a {file_type!r} file, not a HEC-RAS results file."
            )
        projection = _attr(handle, "Projection")
        if not projection:
            raise ResultsError(
                f"{hdf_path.name} carries no 'Projection' attribute.",
                hint="Without it the output raster would have no coordinate system, "
                "and hard coding one is not acceptable here.",
            )
        if _MESH_ROOT not in handle:
            raise ResultsError(
                f"{hdf_path.name} contains no 2D flow areas.",
                hint="This plan is probably a 1D steady run; a depth grid needs a 2D mesh.",
            )

        info = handle.get("Plan Data/Plan Information")
        geometry = handle.get("Geometry")
        unsteady = handle.get("Results/Unsteady")

        names = [
            n.decode("latin-1").strip() if isinstance(n, bytes) else str(n)
            for n in handle[f"{_MESH_ROOT}/Attributes"]["Name"]
        ] if f"{_MESH_ROOT}/Attributes" in handle else [
            k for k in handle[_MESH_ROOT] if isinstance(handle[f"{_MESH_ROOT}/{k}"], h5py.Group)
        ]
        meshes = tuple(_read_mesh(handle, name) for name in names)
        if not meshes:
            raise ResultsError(f"{hdf_path.name} lists no named 2D flow areas.")

        return PlanResults(
            hdf_path=hdf_path,
            projection_wkt=projection,
            plan_title=_attr(info, "Plan Title") or "",
            plan_short_id=_attr(info, "Plan ShortID") or _attr(unsteady, "Short ID") or "",
            plan_filename=_attr(info, "Plan Filename") or "",
            geometry_filename=_attr(info, "Geometry Filename") or "",
            geometry_title=_attr(info, "Geometry Title") or "",
            flow_filename=_attr(info, "Flow Filename") or "",
            flow_title=_attr(info, "Flow Title") or "",
            program_version=_attr(handle, "File Version") or "",
            simulation_window=_attr(info, "Time Window")
            or _attr(unsteady, "Simulation Time Window")
            or "",
            terrain_filename=_attr(geometry, "Terrain Filename") or "",
            terrain_layer=_attr(geometry, "Terrain Layername") or "",
            meshes=meshes,
        )
