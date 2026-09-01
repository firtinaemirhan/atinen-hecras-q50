"""Turn per-cell maximum water surface into a maximum-depth grid.

HEC-RAS 2D results are stored per computation cell, but a cell is not flat:
the model carries sub-grid terrain inside it.  A depth map is therefore built
at terrain resolution, not cell resolution:

    depth(pixel) = water surface over the pixel - terrain elevation at the pixel

Pixels where the result is not positive are dry and become nodata.

The water surface itself is built in :mod:`q50depth.surface`, which offers the
two models RASMapper offers.  Which one to use is not a matter of taste: the
project's ``.rasmap`` file records the mode its own maps were drawn with, and
this data set says ``sloping``.  Drawing a flat surface per cell instead
produces a visibly different map -- on the delivered Q50 reference it shares
54.7% of its wet area, against 72.8% for the sloping surface.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.warp import reproject
from rasterio.windows import Window

from . import surface as surface_model
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
    render_mode: str


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


def grid_of(path) -> Grid:
    """The pixel grid of an existing raster, to build an output on top of it.

    Used by ``--grid-like``: the client's reference maps do not sit on the
    terrain's own pixel boundaries -- they were resampled somewhere in map
    production and their origin is about half a pixel off -- so a map built on
    the terrain grid can never be compared to them cell for cell.  Reading
    their grid back lets the output land on exactly the same pixels.
    """
    with rasterio.open(path) as source:
        return Grid(source.transform, int(source.width), int(source.height))


def read_terrain(
    terrain: Terrain, bounds, resolution: float | None, grid: Grid | None = None
) -> tuple[np.ndarray, Grid]:
    """Read terrain elevation over ``bounds`` and apply its modifications.

    ``grid`` overrides both ``bounds`` and ``resolution``: the terrain is then
    resampled onto that grid instead of being read on its own pixels.
    """
    with rasterio.open(terrain.raster_path) as source:
        # `or` would swallow a legitimate nodata of 0.0, so test for None.
        nodata = source.nodata if source.nodata is not None else -9999.0
        if grid is not None:
            elevation = np.full(grid.shape, np.float32(nodata), dtype="float32")
            reproject(
                source=rasterio.band(source, 1),
                destination=elevation,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=nodata,
                dst_transform=grid.transform,
                dst_crs=source.crs,
                dst_nodata=nodata,
                # Nearest keeps every terrain value one the terrain actually
                # holds. Interpolating ground elevations would invent a bed
                # that HEC-RAS never computed against.
                resampling=Resampling.nearest,
            )
        elif resolution is None or np.isclose(resolution, abs(source.transform.a)):
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


#: A cell that never got wet is reported with a maximum water surface equal to
#: its own minimum elevation -- but only to within float32.  On the delivered
#: Q50 results 1247 cells come back 0.0001 m "deep", which is rounding, not
#: water.  That matters far more than it sounds: those cells sit on the
#: buildings raised 20 m by a terrain modification, and letting one into the
#: sloping surface drags the water surface at a shared corner up with it,
#: producing depths of 13.5 m next to it.  One millimetre is small enough to
#: keep any real result and large enough to clear the rounding.
DEFAULT_WET_TOLERANCE = 0.001


def build(
    results: PlanResults,
    terrain: Terrain,
    resolution: float | None = None,
    min_depth: float = 0.0,
    wet_tolerance: float = DEFAULT_WET_TOLERANCE,
    render_mode: str = "sloping",
    grid: Grid | None = None,
) -> DepthResult:
    """Compute the maximum-depth grid for every 2D area in the results."""
    bounds = mesh_bounds(results.meshes)
    elevation, grid = read_terrain(terrain, bounds, resolution, grid)

    water_surface = np.full(grid.shape, np.nan, dtype="float32")
    wet_cells = total_cells = 0
    for mesh in results.meshes:
        selected = mesh.wet_cells(wet_tolerance)
        wet_cells += int(selected.sum())
        total_cells += int(mesh.real_cells.sum())
        if not selected.any():
            continue
        water_surface = np.fmax(
            water_surface, surface_model.build(mesh, selected, grid, render_mode)
        )

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
        render_mode=render_mode,
    )
