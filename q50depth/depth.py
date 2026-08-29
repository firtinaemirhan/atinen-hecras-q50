"""Turn per-cell maximum water surface into a maximum-depth grid.

HEC-RAS 2D results are stored per computation cell, but a cell is not flat:
the model carries sub-grid terrain inside it.  A depth map is therefore built
at terrain resolution, not cell resolution:

    depth(pixel) = max water surface of the cell covering the pixel
                 - terrain elevation at the pixel

which is how RASMapper renders a maximum-depth layer.  Pixels where the result
is not positive are dry and become nodata.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.windows import Window

from .errors import TerrainError
from .results import Mesh, PlanResults
from .terrain import Terrain


@dataclass(frozen=True)
class Grid:
    transform: Affine
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def resolution(self) -> float:
        return abs(self.transform.a)


@dataclass(frozen=True)
class DepthResult:
    depth: np.ndarray  # float32, NaN where dry or outside the mesh
    grid: Grid
    terrain_min: float
    terrain_max: float
    wet_cells: int
    total_cells: int
    wet_pixels: int
    max_depth: float
    mean_depth: float
    max_water_surface: float


def mesh_bounds(meshes: tuple[Mesh, ...]) -> tuple[float, float, float, float]:
    corners = np.vstack([m.face_point_xy for m in meshes])
    return (
        float(corners[:, 0].min()),
        float(corners[:, 1].min()),
        float(corners[:, 0].max()),
        float(corners[:, 1].max()),
    )


def _grid_aligned_to(source: rasterio.DatasetReader, bounds) -> tuple[Grid, Window]:
    """Grid snapped to the terrain's own pixels, so terrain is read verbatim."""
    left, bottom, right, top = bounds
    transform = source.transform
    col_start, row_start = ~transform @ (left, top)
    col_stop, row_stop = ~transform @ (right, bottom)
    col_start, row_start = int(np.floor(col_start)), int(np.floor(row_start))
    col_stop, row_stop = int(np.ceil(col_stop)), int(np.ceil(row_stop))
    window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
    return (
        Grid(source.window_transform(window), int(window.width), int(window.height)),
        window,
    )


def _grid_at_resolution(bounds, resolution: float) -> Grid:
    """Grid snapped to whole multiples of the requested resolution."""
    left, bottom, right, top = bounds
    left = np.floor(left / resolution) * resolution
    bottom = np.floor(bottom / resolution) * resolution
    right = np.ceil(right / resolution) * resolution
    top = np.ceil(top / resolution) * resolution
    width = int(round((right - left) / resolution))
    height = int(round((top - bottom) / resolution))
    return Grid(Affine(resolution, 0, left, 0, -resolution, top), width, height)


def read_terrain(terrain: Terrain, bounds, resolution: float | None) -> tuple[np.ndarray, Grid]:
    """Read terrain elevation over ``bounds`` and apply its modifications."""
    with rasterio.open(terrain.raster_path) as source:
        # `or` would swallow a legitimate nodata of 0.0, so test for None.
        nodata = source.nodata if source.nodata is not None else -9999.0
        if resolution is None or np.isclose(resolution, abs(source.transform.a)):
            grid, window = _grid_aligned_to(source, bounds)
            elevation = source.read(
                1, window=window, boundless=True, fill_value=nodata
            ).astype("float32")
        else:
            grid = _grid_at_resolution(bounds, resolution)
            window = rasterio.windows.from_bounds(
                *rasterio.transform.array_bounds(grid.height, grid.width, grid.transform)[:4],
                transform=source.transform,
            )
            elevation = source.read(
                1,
                window=window,
                out_shape=grid.shape,
                boundless=True,
                fill_value=nodata,
                resampling=(
                    Resampling.average
                    if resolution > abs(source.transform.a)
                    else Resampling.bilinear
                ),
            ).astype("float32")

    elevation[elevation == np.float32(nodata)] = np.nan
    elevation[elevation < -9000] = np.nan  # also catches boundless fill

    if terrain.modifications:
        shapes = [(m.geojson(), m.value) for m in terrain.modifications]
        # all_touched keeps the boundary pixel of a footprint on the building
        # side; leaving it on the ground side leaves a one-pixel ring of
        # spurious deep water around every building. MergeAlg.replace means
        # overlapping footprints raise the ground once, not once per polygon.
        adjustment = rasterize(
            shapes,
            out_shape=grid.shape,
            transform=grid.transform,
            fill=0.0,
            dtype="float32",
            all_touched=True,
            merge_alg=rasterio.enums.MergeAlg.replace,
        )
        elevation = elevation + adjustment

    if not np.isfinite(elevation).any():
        raise TerrainError(
            f"Terrain {terrain.raster_path.name} has no valid elevation over the model extent.",
            hint="The terrain and the 2D mesh may be in different coordinate systems.",
        )
    return elevation, grid


def _horizontal_surface(mesh: Mesh, selected: np.ndarray, grid: Grid) -> np.ndarray:
    """Paint each wet cell with its own maximum water surface.

    This is what the model actually solves: one water surface value per
    computation cell. Sub-grid ground inside a cell that stands above that
    value simply stays dry, which is why the flood edge looks ragged rather
    than smooth.

    Interpolating a sloping surface between cell centres instead was tried and
    rejected; see "A surface method that was tried and dropped" in README.md.
    """
    shapes = list(_cell_polygons(mesh, selected))
    if not shapes:
        return np.full(grid.shape, np.nan, dtype="float32")
    return rasterize(
        shapes,
        out_shape=grid.shape,
        transform=grid.transform,
        fill=np.nan,
        dtype="float32",
    )


def _cell_polygons(mesh: Mesh, selected: np.ndarray):
    """Yield (GeoJSON polygon, max water surface) for each selected cell.

    ``Cells FacePoint Indexes`` lists a cell's corners but not in ring order,
    so the corners are sorted by their angle around the cell centre.  HEC-RAS
    2D cells are convex, which makes that ordering the polygon boundary.
    """
    face_points = mesh.face_point_xy
    indexes = mesh.cell_face_points
    valid = indexes >= 0
    for cell in np.flatnonzero(selected):
        corners = face_points[indexes[cell][valid[cell]]]
        centre = mesh.cell_center_xy[cell]
        order = np.argsort(
            np.arctan2(corners[:, 1] - centre[1], corners[:, 0] - centre[0])
        )
        ring = corners[order]
        ring = np.vstack([ring, ring[:1]])
        yield {"type": "Polygon", "coordinates": [ring.tolist()]}, float(
            mesh.max_water_surface[cell]
        )


def build(
    results: PlanResults,
    terrain: Terrain,
    resolution: float | None = None,
    min_depth: float = 0.0,
    wet_tolerance: float = 0.0,
) -> DepthResult:
    """Compute the maximum-depth grid for every 2D area in the results."""
    bounds = mesh_bounds(results.meshes)
    elevation, grid = read_terrain(terrain, bounds, resolution)

    water_surface = np.full(grid.shape, np.nan, dtype="float32")
    wet_cells = total_cells = 0
    for mesh in results.meshes:
        selected = mesh.wet_cells(wet_tolerance)
        wet_cells += int(selected.sum())
        total_cells += int(mesh.real_cells.sum())
        if not selected.any():
            continue
        water_surface = np.fmax(water_surface, _horizontal_surface(mesh, selected, grid))

    depth = water_surface - elevation
    depth[~np.isfinite(depth)] = np.nan
    depth[depth <= max(min_depth, 0.0)] = np.nan

    wet = np.isfinite(depth)
    return DepthResult(
        depth=depth,
        grid=grid,
        terrain_min=float(np.nanmin(elevation)),
        terrain_max=float(np.nanmax(elevation)),
        wet_cells=wet_cells,
        total_cells=total_cells,
        wet_pixels=int(wet.sum()),
        max_depth=float(np.nanmax(depth)) if wet.any() else 0.0,
        mean_depth=float(np.nanmean(depth)) if wet.any() else 0.0,
        max_water_surface=float(np.nanmax(water_surface)) if wet.any() else float("nan"),
    )
