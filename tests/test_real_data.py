"""End-to-end check against the delivered data set.

Skipped automatically when the data is not present, because it is client data
and is not part of this repository. Point Q50_CASE_DATA at the folder to run
it, or leave it at the default location.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from q50depth import depth, project, results, terrain, verify
from q50depth.cli import main

CASE_DATA = Path(os.environ.get("Q50_CASE_DATA", Path.home() / "Desktop/CASE_DATA 2"))

#: The client's own Q50 depth map, delivered alongside the model. It is the
#: thing the output has to agree with, so the agreement is pinned by a test
#: rather than left to a one-off measurement.
REFERENCE = (
    CASE_DATA / "AKA_AFY_BAY_INPINAR_1" / "3_Pafta" / "6_derinlik" / "q50_d.tif"
)

pytestmark = pytest.mark.skipif(
    not CASE_DATA.exists(), reason=f"case data not present at {CASE_DATA}"
)


@pytest.fixture(scope="module")
def selected():
    prj = project.find_project_file(CASE_DATA)
    loaded = project.load_project(prj)
    plan, evidence = project.select_plan(loaded, "Q50")
    return loaded, plan, evidence


def test_selects_p05_and_nothing_else(selected):
    loaded, plan, evidence = selected
    assert [p.number for p in loaded.plans] == ["p03", "p02", "p01", "p04", "p05", "p06", "p07"]
    assert plan.number == "p05"
    assert plan.short_id == "Q50"
    assert set(evidence) == {"p05"}


def test_the_stray_backup_plan_is_on_disk_but_not_selected(selected):
    loaded, plan, _ = selected
    stray = loaded.folder / "Backup.p01"
    assert stray.is_file(), "the trap file is expected in the delivered data"
    assert "Q50" in stray.read_text(encoding="latin-1")
    assert plan.path.name == "A_A_B_INPINAR.p05"


def test_full_pipeline_on_existing_results(selected, tmp_path: Path):
    loaded, plan, _ = selected
    plan_results = results.load(results.results_path_for(plan.path))
    assert plan_results.plan_short_id == "Q50"
    assert plan_results.terrain_layer == "merge.Clone"

    model_terrain = terrain.resolve(loaded.folder, plan_results.terrain_filename)
    assert len(model_terrain.modifications) == 69

    grid = depth.build(plan_results, model_terrain)
    # Cell-level maximum depth is 1.42 m; at 0.1 m terrain resolution the
    # deepest pixel sits slightly below the cell's mean bed.
    assert 1.0 < grid.max_depth < 2.0
    assert 0.05 < grid.mean_depth < 0.5
    assert grid.wet_pixels > 100_000

    checks = verify.run(loaded, plan, "Q50", plan_results, grid)
    assert all(c.passed for c in checks)


@pytest.mark.skipif(not REFERENCE.is_file(), reason=f"no reference map at {REFERENCE}")
def test_sloping_surface_agrees_with_the_client_reference_map(selected, tmp_path: Path):
    """The sloping surface must stay close to the map the client produced.

    Measured on the reference's own grid and at its own floor (its smallest
    value is 0.0050 m), so the only thing being compared is the water surface.
    The thresholds are set just under what is measured today, to catch a
    regression rather than to restate the measurement:

        shared wet area   72.82%   mean absolute difference   0.0187 m
        bias             -0.0008 m   maximum   1.5724 m (reference 1.5705 m)
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tools.compare_reference import compare

    loaded, plan, _ = selected
    plan_results = results.load(results.results_path_for(plan.path))
    model_terrain = terrain.resolve(loaded.folder, plan_results.terrain_filename)

    built = depth.build(
        plan_results,
        model_terrain,
        min_depth=0.005,
        grid=depth.grid_of(REFERENCE),
    )
    assert built.render_mode == "sloping"

    output = tmp_path / "q50_on_reference_grid.tif"
    from q50depth import raster

    raster.write(output, built, plan_results.projection_wkt, {})
    stats = compare(output, REFERENCE)

    assert stats["iou"] > 0.70, "agreement with the client's map has regressed"
    assert stats["mean_absolute"] < 0.025
    assert abs(stats["bias"]) < 0.005
    assert 1.55 < built.max_depth < 1.60


def test_flat_surface_is_the_one_that_disagrees(selected):
    """Pins the defect that made the first delivery's map a different map.

    Kept as a test because the number is the argument: drawing one level per
    cell is not a stylistic difference from RASMapper, it moves the flood
    edge over 96,000 pixels of ground.
    """
    loaded, plan, _ = selected
    plan_results = results.load(results.results_path_for(plan.path))
    model_terrain = terrain.resolve(loaded.folder, plan_results.terrain_filename)

    flat = depth.build(plan_results, model_terrain, render_mode="flat")
    sloping = depth.build(plan_results, model_terrain)
    assert flat.wet_pixels > sloping.wet_pixels + 50_000
    assert flat.max_depth > sloping.max_depth


def test_the_project_asks_for_the_sloping_surface(selected):
    """The render mode is read from the project, not chosen by this code."""
    from q50depth import surface

    loaded, _, _ = selected
    rasmap = loaded.prj_path.with_suffix(".rasmap")
    assert rasmap.is_file()
    assert surface.read_render_mode(rasmap) == "sloping"


def test_cli_writes_a_readable_geotiff(tmp_path: Path):
    import rasterio

    output = tmp_path / "q50_depth.tif"
    code = main(
        [
            "--project", str(CASE_DATA),
            "--use-existing-results",
            "--output", str(output),
        ]
    )
    assert code == 0
    with rasterio.open(output) as raster:
        tags = raster.tags()
        assert tags["SCENARIO"] == "Q50"
        assert tags["PLAN_NUMBER"] == "p05"
        assert tags["PLAN_SHORT_ID"] == "Q50"
        assert raster.crs is not None
        assert raster.nodata == -9999.0
