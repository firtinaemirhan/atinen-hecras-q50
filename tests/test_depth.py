"""Depth arithmetic, on a mesh small enough to reason about by hand.

Two 5x5 m cells on flat 100 m ground:

    cell 0: x 0..5   wet, maximum water surface 100.5. A building covers
                     x 0..1 of it, so only x 1..5 is really under water.
    cell 1: x 5..10  never got wet. A building covers x 5..9 of it and its bed
                     sits on that building, so HEC-RAS reports its maximum
                     water surface as 120.0 -- its own bed, not water.

Both traps are here. Ignoring the building modification floods the building in
cell 0; ignoring the dry-cell rule paints a 20 m lake over the strip of cell 1
that the building does not cover.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from q50depth import depth, results, surface, terrain
from q50depth.errors import TerrainError
from tests.synthetic import write_results_hdf, write_terrain_hdf, write_terrain_raster

FACE_POINTS = np.array(
    [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0], [10.0, 0.0], [10.0, 5.0]]
)
# cell 0, cell 1, and a padded ghost cell such as HEC-RAS appends
CELL_FACE_POINTS = np.array([[0, 1, 2, 3], [1, 4, 5, 2], [0, 1, -1, -1]])
CELL_CENTERS = np.array([[2.5, 2.5], [7.5, 2.5], [0.0, 0.0]])
BUILDING_IN_DRY_CELL = [[5.0, 0.0], [9.0, 0.0], [9.0, 5.0], [5.0, 5.0], [5.0, 0.0]]
BUILDING_IN_WET_CELL = [[0.0, 0.0], [1.0, 0.0], [1.0, 5.0], [0.0, 5.0], [0.0, 0.0]]
BUILDINGS = [
    (BUILDING_IN_DRY_CELL, 20.0, "Add"),
    (BUILDING_IN_WET_CELL, 20.0, "Add"),
]


@pytest.fixture
def scene(tmp_path: Path):
    write_terrain_raster(tmp_path / "ground.tif", elevation=100.0, size=10)
    write_terrain_hdf(tmp_path / "ground.hdf", BUILDINGS)
    write_results_hdf(
        tmp_path / "plan.p05.hdf",
        face_points=FACE_POINTS,
        cell_face_points=CELL_FACE_POINTS,
        cell_centers=CELL_CENTERS,
        cell_min_elevation=np.array([100.0, 120.0, np.nan]),
        max_water_surface=np.array([100.5, 120.0, 0.0]),
        terrain_filename=r".\ground.hdf",
    )
    loaded = results.load(tmp_path / "plan.p05.hdf")
    return loaded, terrain.resolve(tmp_path, loaded.terrain_filename)


def test_ghost_cells_are_excluded(scene):
    loaded, _ = scene
    mesh = loaded.meshes[0]
    assert mesh.cell_count == 3
    assert mesh.real_cells.tolist() == [True, True, False]


def test_dry_cell_on_a_raised_footprint_is_not_wet(scene):
    loaded, _ = scene
    mesh = loaded.meshes[0]
    assert mesh.wet_cells().tolist() == [True, False, False]


def test_depth_is_water_surface_minus_terrain(scene):
    loaded, model_terrain = scene
    result = depth.build(loaded, model_terrain)
    assert result.wet_cells == 1
    assert result.max_depth == pytest.approx(0.5)
    assert result.mean_depth == pytest.approx(0.5)
    # cell 0 is 5 x 5 m, minus the 1 x 5 m building standing in it
    assert result.wet_pixels == 20


def test_building_modification_is_applied_to_the_terrain(scene):
    _, model_terrain = scene
    assert len(model_terrain.modifications) == 2
    elevation, _ = depth.read_terrain(model_terrain, (0.0, 0.0, 10.0, 10.0), None)
    assert np.nanmax(elevation) == pytest.approx(120.0)
    assert np.nanmin(elevation) == pytest.approx(100.0)


def test_without_the_dry_cell_rule_the_building_would_flood(scene):
    """Pins the failure mode the wet-cell rule exists to prevent."""
    loaded, model_terrain = scene
    mesh = loaded.meshes[0]
    everything = mesh.real_cells  # i.e. skip the wet_cells() filter
    elevation, grid = depth.read_terrain(model_terrain, (0.0, 0.0, 10.0, 10.0), None)
    naive = surface.flat(mesh, everything, grid) - elevation
    assert np.nanmax(naive) == pytest.approx(20.0)


def test_building_inside_a_wet_cell_stays_dry(scene):
    """Without the terrain modification these 5 pixels would report 0.5 m."""
    loaded, model_terrain = scene
    result = depth.build(loaded, model_terrain)
    import rasterio.transform

    rows, cols = rasterio.transform.rowcol(
        result.grid.transform, [0.5] * 5, [0.5, 1.5, 2.5, 3.5, 4.5]
    )
    assert np.all(np.isnan(result.depth[rows, cols]))


def test_min_depth_filters_thin_films(scene):
    loaded, model_terrain = scene
    assert depth.build(loaded, model_terrain, min_depth=1.0).wet_pixels == 0


def test_coarser_resolution_still_produces_water(scene):
    loaded, model_terrain = scene
    result = depth.build(loaded, model_terrain, resolution=2.5)
    assert result.grid.resolution == pytest.approx(2.5)
    assert result.wet_pixels > 0


def test_unsupported_modification_type_is_refused(tmp_path: Path):
    write_terrain_raster(tmp_path / "ground.tif")
    write_terrain_hdf(tmp_path / "ground.hdf", [(BUILDING_IN_DRY_CELL, 20.0, "Set")])
    with pytest.raises(TerrainError, match="unsupported elevation modification"):
        terrain.resolve(tmp_path, r".\ground.hdf")


def test_missing_terrain_raster_is_refused(tmp_path: Path):
    write_terrain_hdf(tmp_path / "ground.hdf", [])
    with pytest.raises(TerrainError, match="no elevation raster"):
        terrain.resolve(tmp_path, r".\ground.hdf")
