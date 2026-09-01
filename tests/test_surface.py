"""The two water surfaces RASMapper can draw, on a mesh small enough to check by hand.

Two 5 x 5 m cells side by side on flat 100 m ground:

    cell 0: x 0..5   maximum water surface 101.0
    cell 1: x 5..10  maximum water surface 103.0

They share the edge x = 5.  A flat surface therefore steps from 101 to 103
across that edge; a sloping surface passes through 102 on it, because the two
corners on the edge are shared and average the cells that meet there.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from q50depth import depth, results, surface, terrain
from tests.synthetic import write_results_hdf, write_terrain_hdf, write_terrain_raster

FACE_POINTS = np.array(
    [[0.0, 0.0], [5.0, 0.0], [5.0, 5.0], [0.0, 5.0], [10.0, 0.0], [10.0, 5.0]]
)
CELL_FACE_POINTS = np.array([[0, 1, 2, 3], [1, 4, 5, 2]])
CELL_CENTERS = np.array([[2.5, 2.5], [7.5, 2.5]])
BOUNDS = (0.0, 0.0, 10.0, 5.0)


def _scene(tmp_path: Path, max_water_surface, cell_min_elevation=(100.0, 100.0),
           modifications=(), areas=None):
    write_terrain_raster(tmp_path / "ground.tif", elevation=100.0, size=10)
    write_terrain_hdf(tmp_path / "ground.hdf", list(modifications))
    write_results_hdf(
        tmp_path / "plan.p05.hdf",
        face_points=FACE_POINTS,
        cell_face_points=CELL_FACE_POINTS,
        cell_centers=CELL_CENTERS,
        cell_min_elevation=np.array(cell_min_elevation),
        max_water_surface=np.array(max_water_surface),
        terrain_filename=r".\ground.hdf",
        cell_surface_area=None if areas is None else np.array(areas),
    )
    loaded = results.load(tmp_path / "plan.p05.hdf")
    return loaded, terrain.resolve(tmp_path, loaded.terrain_filename)


@pytest.fixture
def two_wet_cells(tmp_path: Path):
    return _scene(tmp_path, max_water_surface=(101.0, 103.0))


def _grid(model_terrain):
    _, grid = depth.read_terrain(model_terrain, BOUNDS, None)
    return grid


def _at(values, grid, x, y):
    """Value at the pixel whose centre is nearest (x, y)."""
    col = int((x - grid.transform.c) / grid.transform.a)
    row = int((y - grid.transform.f) / grid.transform.e)
    return float(values[row, col])


def test_face_point_cells_inverts_the_cell_table(two_wet_cells):
    loaded, _ = two_wet_cells
    neighbours = surface.face_point_cells(loaded.meshes[0])
    assert neighbours[0].tolist() == [0]  # corner (0,0): only cell 0
    assert neighbours[1].tolist() == [0, 1]  # corner (5,0): shared
    assert neighbours[2].tolist() == [0, 1]  # corner (5,5): shared
    assert neighbours[4].tolist() == [1]  # corner (10,0): only cell 1


def test_shared_corner_averages_the_cells_that_meet_there(two_wet_cells):
    loaded, _ = two_wet_cells
    mesh = loaded.meshes[0]
    at_corner = surface.face_point_water_surface(mesh, mesh.wet_cells())
    assert at_corner[0] == pytest.approx(101.0)  # cell 0 alone
    assert at_corner[1] == pytest.approx(102.0)  # (101 + 103) / 2
    assert at_corner[2] == pytest.approx(102.0)
    assert at_corner[4] == pytest.approx(103.0)  # cell 1 alone


def test_corner_average_is_weighted_by_cell_surface_area(tmp_path: Path):
    """A big cell and a small one meeting at a corner do not weigh the same."""
    loaded, _ = _scene(
        tmp_path, max_water_surface=(101.0, 103.0), areas=(30.0, 10.0)
    )
    mesh = loaded.meshes[0]
    at_corner = surface.face_point_water_surface(mesh, mesh.wet_cells())
    # (101*30 + 103*10) / 40
    assert at_corner[1] == pytest.approx(101.5)
    unweighted = surface.face_point_water_surface(
        mesh, mesh.wet_cells(), weight_by_area=False
    )
    assert unweighted[1] == pytest.approx(102.0)


def test_flat_surface_steps_at_the_shared_edge(two_wet_cells):
    loaded, model_terrain = two_wet_cells
    mesh = loaded.meshes[0]
    grid = _grid(model_terrain)
    painted = surface.flat(mesh, mesh.wet_cells(), grid)
    assert _at(painted, grid, 2.5, 2.5) == pytest.approx(101.0)
    assert _at(painted, grid, 4.5, 2.5) == pytest.approx(101.0)
    assert _at(painted, grid, 5.5, 2.5) == pytest.approx(103.0)
    assert _at(painted, grid, 7.5, 2.5) == pytest.approx(103.0)


def test_sloping_surface_is_continuous_across_the_shared_edge(two_wet_cells):
    loaded, model_terrain = two_wet_cells
    mesh = loaded.meshes[0]
    grid = _grid(model_terrain)
    painted = surface.sloping(mesh, mesh.wet_cells(), grid)
    left = _at(painted, grid, 4.5, 2.5)
    right = _at(painted, grid, 5.5, 2.5)
    # Either side of the edge the surface is close to the corner value of 102,
    # and the jump the flat surface makes (2.0 m) is gone.
    assert abs(right - left) < 0.5
    assert 101.5 < left < 102.0
    assert 102.0 < right < 102.5


def test_sloping_surface_interpolates_barycentrically(two_wet_cells):
    """Pins one pixel arithmetic can be done on by hand.

    The pixel centred at (4.5, 2.5) lies in cell 0's triangle
    (5,0)-(5,5)-(2.5,2.5), whose corner heights are 102, 102 and 101.  Its
    barycentric coordinates there are 0.4, 0.4 and 0.2, so the surface is
    0.4*102 + 0.4*102 + 0.2*101 = 101.8.
    """
    loaded, model_terrain = two_wet_cells
    mesh = loaded.meshes[0]
    grid = _grid(model_terrain)
    painted = surface.sloping(mesh, mesh.wet_cells(), grid)
    assert _at(painted, grid, 4.5, 2.5) == pytest.approx(101.8, abs=1e-4)


def test_one_wet_cell_alone_gives_a_level_surface(tmp_path: Path):
    """With no wet neighbour every corner takes the cell's own value."""
    loaded, model_terrain = _scene(
        tmp_path, max_water_surface=(101.0, 100.0)  # cell 1 never got wet
    )
    mesh = loaded.meshes[0]
    grid = _grid(model_terrain)
    painted = surface.sloping(mesh, mesh.wet_cells(), grid)
    wet = painted[np.isfinite(painted)]
    assert wet.size > 0
    assert np.allclose(wet, 101.0)


def test_unknown_render_mode_is_refused(two_wet_cells):
    loaded, model_terrain = two_wet_cells
    mesh = loaded.meshes[0]
    with pytest.raises(ValueError, match="Unknown render mode"):
        surface.build(mesh, mesh.wet_cells(), _grid(model_terrain), "smooth")


# --- the rounding trap -------------------------------------------------------

BUILDING = [[5.0, 0.0], [10.0, 0.0], [10.0, 5.0], [5.0, 5.0], [5.0, 0.0]]


@pytest.fixture
def noise_wet_building(tmp_path: Path):
    """Cell 1 sits on a 20 m building and is 0.0001 m "deep" -- rounding, not water.

    This is the shape of the trap in the delivered Q50 results, where 1247
    cells come back exactly 0.0001 m above their own bed.
    """
    return _scene(
        tmp_path,
        max_water_surface=(100.5, 120.0001),
        cell_min_elevation=(100.0, 120.0),
        modifications=[(BUILDING, 20.0, "Add")],
    )


def test_rounding_deep_cell_is_not_wet_by_default(noise_wet_building):
    loaded, _ = noise_wet_building
    mesh = loaded.meshes[0]
    assert mesh.wet_cells(depth.DEFAULT_WET_TOLERANCE).tolist() == [True, False]


def test_rounding_deep_cell_would_lift_the_sloping_surface(noise_wet_building):
    """Without the tolerance the building drags its neighbour's water up.

    Cell 1's corners are shared with cell 0, so a surface that counts cell 1
    as wet averages 100.5 with 120.0001 and lays 8.3 m of water over the
    ground in cell 0.  This is the failure the tolerance exists to prevent;
    on the real Q50 mesh the same trap produces 13.5 m.
    """
    loaded, model_terrain = noise_wet_building
    mesh = loaded.meshes[0]
    grid = _grid(model_terrain)
    elevation, _ = depth.read_terrain(model_terrain, BOUNDS, None)

    counted = surface.sloping(mesh, mesh.wet_cells(0.0), grid) - elevation
    assert np.nanmax(counted) == pytest.approx(8.3, abs=0.01)

    excluded = surface.sloping(
        mesh, mesh.wet_cells(depth.DEFAULT_WET_TOLERANCE), grid
    ) - elevation
    assert np.nanmax(excluded) == pytest.approx(0.5)


def test_build_defaults_to_the_sloping_surface(noise_wet_building):
    loaded, model_terrain = noise_wet_building
    result = depth.build(loaded, model_terrain)
    assert result.render_mode == "sloping"
    assert result.max_depth == pytest.approx(0.5)
