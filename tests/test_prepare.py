"""Making a working copy that HEC-RAS can actually load.

The delivered project declares seven plans; five of them cannot be assembled
(one names an unsteady flow file the project never declares, four read a
boundary condition from a path that does not resolve). HEC-RAS loads every
declared plan when a project is opened, so those five abort the load for the
whole project -- including the one plan that is fine.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from q50depth import compute, project
from q50depth.errors import ComputeError

STEM = "MODEL"


def write_project(folder: Path, body: str) -> Path:
    path = folder / f"{STEM}.prj"
    path.write_bytes(body.replace("\n", "\r\n").encode("latin-1"))
    return path


@pytest.fixture
def messy(tmp_path: Path) -> Path:
    """A project shaped like the delivered one: one good plan, two broken."""
    folder = tmp_path / "1_Modeller"
    folder.mkdir()
    for number, geom, flow in (("p05", "g03", "u05"), ("p03", "g03", "u01"), ("p06", "g03", "u06")):
        (folder / f"{STEM}.{number}").write_text(
            f"Plan Title={STEM}_{number}\nShort Identifier={number}\n"
            f"Geom File={geom}\nFlow File={flow}\nDSS File=.\\Q50\\Q50.dss\n",
            encoding="latin-1",
        )
    for name in ("g01", "g03", "u01", "u05", "u06"):
        (folder / f"{STEM}.{name}").write_text("Flow Title=x\n", encoding="latin-1")
    # u06 points at a boundary condition that is not there
    (folder / f"{STEM}.u06").write_text(
        "Flow Title=Q100\nDSS File=.\\gone\\missing.dss\nUse DSS=True\n", encoding="latin-1"
    )
    write_project(
        folder,
        "Proj Title=MODEL\nCurrent Plan=p03\nSI Units\n"
        "Geom File=g01\nGeom File=g03\n"
        "Unsteady File=u05\nUnsteady File=u06\n"
        "Plan File=p05\nPlan File=p03\nPlan File=p06\n"
        "Y Axis Title=Elevation\n"
        "DSS File=dss\nDSS File=.\\Q50\\Q50.dss\nDSS File=.\\Q999\\Q999.dss\n",
    )
    return folder


def test_defects_name_the_plan_and_the_reason(messy: Path):
    loaded = project.load_project(messy / f"{STEM}.prj")
    reasons = {d.plan: d.problem for d in project.plan_defects(loaded)}
    assert "p05" not in reasons, "the good plan must not be flagged"
    assert "u01 is not declared" in reasons["p03"]
    assert "does not resolve" in reasons["p06"]


def test_reduced_project_declares_only_the_selected_plan(messy: Path):
    prj = messy / f"{STEM}.prj"
    loaded = project.load_project(prj)
    plan = next(p for p in loaded.plans if p.number == "p05")
    project.write_reduced(prj, plan)

    after = project.load_project(prj)
    assert [p.number for p in after.plans] == ["p05"]
    assert after.current_plan == "p05"
    assert "Y Axis Title=Elevation" in prj.read_text(encoding="latin-1"), (
        "unrelated settings are kept"
    )


def test_geometry_and_flow_declarations_survive_the_reduction(messy: Path):
    """HEC-RAS numbers its preprocessor output (.xNN) from the geometry list.

    Dropping entries makes it look for a file that was never delivered, ask to
    run the preprocessor, and then rebuild -- and lose -- the structure tables.
    """
    prj = messy / f"{STEM}.prj"
    loaded = project.load_project(prj)
    plan = next(p for p in loaded.plans if p.number == "p05")
    project.write_reduced(prj, plan)

    text = prj.read_text(encoding="latin-1")
    assert "Geom File=g01" in text and "Geom File=g03" in text
    assert "Unsteady File=u05" in text and "Unsteady File=u06" in text


def test_reduced_project_keeps_crlf(messy: Path):
    prj = messy / f"{STEM}.prj"
    loaded = project.load_project(prj)
    plan = next(p for p in loaded.plans if p.number == "p05")
    project.write_reduced(prj, plan)
    raw = prj.read_bytes()
    assert raw.count(b"\r\n") > 5
    assert raw.count(b"\n") == raw.count(b"\r\n"), "no bare newlines"


def test_reduced_project_drops_dss_entries_that_cannot_be_opened(messy: Path):
    prj = messy / f"{STEM}.prj"
    (messy / "Q50").mkdir()
    loaded = project.load_project(prj)
    plan = next(p for p in loaded.plans if p.number == "p05")
    dropped = project.write_reduced(prj, plan)
    text = prj.read_text(encoding="latin-1")
    assert "DSS File=.\\Q50\\Q50.dss" in text, "its folder exists, so keep it"
    assert "DSS File=dss" not in text, "not a path at all"
    assert "Q999" not in text, "its folder was never delivered"
    assert any("dss" == d.split("=")[1] for d in dropped)


def test_reduced_project_adds_a_declaration_the_project_forgot(messy: Path):
    """p03 uses u01, which the project never declares. Selecting it must fix that."""
    prj = messy / f"{STEM}.prj"
    loaded = project.load_project(prj)
    plan = next(p for p in loaded.plans if p.number == "p03")
    project.write_reduced(prj, plan)
    text = prj.read_text(encoding="latin-1")
    assert "Unsteady File=u01" in text
    assert [p.number for p in project.load_project(prj).plans] == ["p03"]


def test_stale_results_are_removed(tmp_path: Path):
    hdf = tmp_path / "MODEL.p05.hdf"
    assert compute.clear_stale_results(hdf) is False
    hdf.write_bytes(b"leftover")
    assert compute.clear_stale_results(hdf) is True
    assert not hdf.exists()


def _partial_hdf(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        handle.attrs["File Type"] = np.bytes_(b"HEC-RAS Results")
        handle.create_group("Geometry")


def test_verify_results_rejects_a_stub_file_and_quotes_the_hec_ras_log(tmp_path: Path):
    prj = tmp_path / "MODEL.prj"
    prj.write_text("Proj Title=MODEL\n", encoding="latin-1")
    hdf = tmp_path / "MODEL.p05.hdf"
    _partial_hdf(hdf)
    (tmp_path / "MODEL.bco05").write_text(
        "Opening plan\nError in Loading Plan Data\nAborting\n", encoding="latin-1"
    )
    with pytest.raises(ComputeError) as error:
        compute.verify_results(hdf, prj, "p05")
    assert "unfinished" in error.value.message
    assert "Error in Loading Plan Data" in (error.value.hint or "")


def test_verify_results_reports_a_run_that_wrote_nothing(tmp_path: Path):
    prj = tmp_path / "MODEL.prj"
    prj.write_text("Proj Title=MODEL\n", encoding="latin-1")
    with pytest.raises(ComputeError, match="without writing"):
        compute.verify_results(tmp_path / "MODEL.p05.hdf", prj, "p05")


def test_verify_results_accepts_a_finished_run(tmp_path: Path):
    prj = tmp_path / "MODEL.prj"
    prj.write_text("Proj Title=MODEL\n", encoding="latin-1")
    hdf = tmp_path / "MODEL.p05.hdf"
    with h5py.File(hdf, "w") as handle:
        handle.attrs["File Type"] = np.bytes_(b"HEC-RAS Results")
        handle.create_group("Plan Data/Plan Information")
        handle.create_group("Results")
    compute.verify_results(hdf, prj, "p05")  # must not raise


def test_plan_flag_is_changed_in_place(tmp_path: Path):
    plan = tmp_path / "MODEL.p05"
    plan.write_bytes(
        b"Plan Title=X\r\nRun RASMapper=-1\r\nRun PostProcess=-1\r\n"
    )
    assert project.set_plan_flag(plan, "Run RASMapper", " 0 ") == "-1"
    raw = plan.read_bytes()
    assert b"Run RASMapper= 0 \r\n" in raw
    assert b"Run PostProcess=-1" in raw, "other settings untouched"
    assert raw.count(b"\n") == raw.count(b"\r\n"), "CRLF preserved"


def test_plan_flag_reports_a_key_that_is_not_there(tmp_path: Path):
    plan = tmp_path / "MODEL.p05"
    plan.write_bytes(b"Plan Title=X\r\n")
    assert project.set_plan_flag(plan, "Run RASMapper", " 0 ") is None
    assert plan.read_bytes() == b"Plan Title=X\r\n"


def test_compute_messages_file_is_preferred_over_the_run_banner(tmp_path: Path):
    """`.bco` usually holds only the banner; the real reason is in computeMsgs."""
    prj = tmp_path / "MODEL.prj"
    prj.write_text("Proj Title=MODEL\n", encoding="latin-1")
    hdf = tmp_path / "MODEL.p05.hdf"
    _partial_hdf(hdf)
    (tmp_path / "MODEL.bco05").write_text("HEC-RAS banner only\n", encoding="latin-1")
    (tmp_path / "MODEL.p05.computeMsgs.txt").write_text(
        "Reading boundary conditions\nERROR: unable to open DSS file\n", encoding="latin-1"
    )
    with pytest.raises(ComputeError) as error:
        compute.verify_results(hdf, prj, "p05")
    hint = error.value.hint or ""
    assert "unable to open DSS file" in hint
    assert "banner only" not in hint


def test_compute_messages_are_read_from_the_results_file_when_no_log_was_written(tmp_path: Path):
    prj = tmp_path / "MODEL.prj"
    prj.write_text("Proj Title=MODEL\n", encoding="latin-1")
    hdf = tmp_path / "MODEL.p05.hdf"
    with h5py.File(hdf, "w") as handle:
        handle.attrs["File Type"] = np.bytes_(b"HEC-RAS Results")
        handle.create_dataset(
            "Results/Summary/Compute Messages (text)",
            data=np.bytes_(b"Geometry preprocessor\nERROR: terrain not found\n"),
        )
    with pytest.raises(ComputeError) as error:
        compute.verify_results(hdf, prj, "p05")
    assert "terrain not found" in (error.value.hint or "")


BARRELS = "Geometry/Structures/Culvert Groups/Barrels"


def _geometry_file(path: Path, *, complete: bool, culverts: bool = True) -> Path:
    """A miniature geometry shaped like the delivered one.

    ``culverts`` mirrors the delivered model, which declares two SA/2D
    connections with culvert barrels. A model without culverts is not missing
    anything when it has no barrel-to-cell datasets, and that is tested too.
    """
    with h5py.File(path, "w") as handle:
        handle.attrs["File Type"] = np.bytes_(b"HEC-RAS Geometry")
        handle.attrs["Units System"] = np.bytes_(b"SI Units")
        handle.create_group("Geometry/Structures")
        handle.create_dataset(
            "Geometry/Boundary Condition Lines/Attributes",
            data=np.array([(b"inflow",)], dtype=[("Name", "S16")]),
        )
        handle.create_dataset(
            "Geometry/Structures/Attributes",
            data=np.array(
                [(b"Weir/Gate/Culverts", 2 if culverts else 0)],
                dtype=[("Mode", "S18"), ("Culvert Groups", "<i4")],
            ),
        )
        if culverts:
            handle.create_dataset(f"{BARRELS}/Attributes", data=np.arange(4))
        # Present in every real file that has it, and always empty: it is not
        # evidence of anything, which is why it is not in REQUIRED.
        handle.create_group("Geometry/Structures/Property Tables")
        if complete:
            handle.create_dataset("Geometry/GeomPreprocess/Node Info", data=np.arange(3))
            handle.create_dataset(
                "Geometry/Boundary Condition Lines/External Faces",
                data=np.array(
                    [(0, 1, 0, 1), (0, 0, 1, 2)],
                    dtype=[("BC Line ID", "<i4"), ("Face Index", "<i4"),
                           ("FP Start Index", "<i4"), ("FP End Index", "<i4")],
                ),
            )
            if culverts:
                handle.create_dataset(f"{BARRELS}/Upstream Cells", data=np.arange(6))
                handle.create_dataset(f"{BARRELS}/Downstream Cells", data=np.arange(8))
    return path


def test_missing_preprocessed_tables_are_detected(tmp_path: Path):
    from q50depth import geometry

    incomplete = _geometry_file(tmp_path / "MODEL.g03.hdf", complete=False)
    assert geometry.missing_tables(incomplete) == geometry.REQUIRED
    complete = _geometry_file(tmp_path / "other.g03.hdf", complete=True)
    assert geometry.missing_tables(complete) == ()
    assert geometry.missing_tables(tmp_path / "absent.hdf") == geometry.REQUIRED


def test_an_empty_property_tables_group_is_not_taken_as_evidence(tmp_path: Path):
    """The group the first version tested for is empty in every real file.

    Testing for its presence made a geometry with no preprocessor output at all
    look repaired, and made ``--geometry rasprocess`` look like it had failed
    when the question had been asked wrongly.
    """
    from q50depth import geometry

    incomplete = _geometry_file(tmp_path / "MODEL.g03.hdf", complete=False)
    with h5py.File(incomplete, "r") as handle:
        assert "Geometry/Structures/Property Tables" in handle
        assert len(handle["Geometry/Structures/Property Tables"]) == 0
    assert geometry.missing_tables(incomplete) == geometry.REQUIRED


def test_a_model_without_culverts_needs_no_barrel_datasets(tmp_path: Path):
    from q50depth import geometry

    path = _geometry_file(tmp_path / "MODEL.g03.hdf", complete=True, culverts=False)
    assert geometry.missing_tables(path) == ()

    bare = _geometry_file(tmp_path / "bare.g03.hdf", complete=False, culverts=False)
    assert geometry.missing_tables(bare) == (
        "Geometry/GeomPreprocess",
        "Geometry/Boundary Condition Lines/External Faces",
    )


def test_geometry_is_rebuilt_from_the_results_file(tmp_path: Path):
    from q50depth import geometry

    incomplete = _geometry_file(tmp_path / "MODEL.g03.hdf", complete=False)
    results_hdf = _geometry_file(tmp_path / "MODEL.p05.hdf", complete=True)
    with h5py.File(results_hdf, "r+") as handle:
        handle.attrs["File Type"] = np.bytes_(b"HEC-RAS Results")

    repair = geometry.rebuild_from_results(incomplete, results_hdf)
    assert geometry.missing_tables(incomplete) == ()
    assert len(repair.added) == len(geometry.REQUIRED)
    with h5py.File(incomplete, "r") as handle:
        assert handle.attrs["File Type"] == b"HEC-RAS Geometry", "still a geometry file"
        assert "Results" not in handle, "only the Geometry group is taken"


#: Three face points and two faces joining them. The two files below number the
#: faces the other way round, which is the situation the remap exists for: the
#: delivered geometry and the results file disagree about 10678 of 12868 faces.
FACE_POINTS = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]


def _with_mesh(path: Path, centres, faces=((0, 1), (1, 2))) -> Path:
    """Give a geometry file a 2D area, so the graft has numbering to check."""
    with h5py.File(path, "r+") as handle:
        area = "Geometry/2D Flow Areas/inpinar"
        handle.create_dataset(
            f"{area}/Cells Center Coordinate", data=np.asarray(centres, dtype="float64")
        )
        handle.create_dataset(
            f"{area}/FacePoints Coordinate", data=np.asarray(FACE_POINTS, dtype="float64")
        )
        handle.create_dataset(
            f"{area}/Faces FacePoint Indexes", data=np.asarray(faces, dtype="int32")
        )
    return path


CENTRES = [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]


def test_graft_copies_only_what_is_missing(tmp_path: Path):
    """The 2D tables HEC-RAS just built must survive the repair."""
    from q50depth import geometry

    incomplete = _with_mesh(
        _geometry_file(tmp_path / "MODEL.g03.hdf", complete=False), CENTRES
    )
    with h5py.File(incomplete, "r+") as handle:
        handle.create_dataset("Geometry/2D Flow Areas/inpinar/Expensive", data=np.arange(9))
    results_hdf = _with_mesh(
        _geometry_file(tmp_path / "MODEL.p05.hdf", complete=True), CENTRES
    )

    repair = geometry.graft_missing(incomplete, results_hdf)

    assert set(repair.added) == set(geometry.REQUIRED)
    assert geometry.missing_tables(incomplete) == ()
    with h5py.File(incomplete, "r") as handle:
        assert "Geometry/2D Flow Areas/inpinar/Expensive" in handle, "graft destroyed work"
        assert handle.attrs["File Type"] == b"HEC-RAS Geometry"
        assert "Results" not in handle


def test_a_declared_culvert_is_missing_even_when_its_whole_tree_is(tmp_path: Path):
    """The model says whether it has culverts; the missing tables do not.

    Asking whether ``.../Culvert Groups/Barrels`` exists is circular: the
    delivered geometry has no Culvert Groups tree at all, so that test decided
    the model had no culverts and stopped requiring the datasets it was missing.
    The graft then copied one of three and the engine died one stage later, in
    JOBINIT_Q2D_BC instead of READ_UN_HDF_STRUC.
    """
    from q50depth import geometry

    path = _with_mesh(_geometry_file(tmp_path / "MODEL.g03.hdf", complete=True), CENTRES)
    with h5py.File(path, "r+") as handle:
        del handle["Geometry/Structures/Culvert Groups"]
    assert geometry.missing_tables(path) == (
        f"{BARRELS}/Upstream Cells",
        f"{BARRELS}/Downstream Cells",
    )


def test_graft_restores_a_whole_missing_branch(tmp_path: Path):
    """Creating empty parents and dropping in leaves loses the rest of the tree."""
    from q50depth import geometry

    incomplete = _with_mesh(
        _geometry_file(tmp_path / "MODEL.g03.hdf", complete=True), CENTRES
    )
    with h5py.File(incomplete, "r+") as handle:
        del handle["Geometry/Structures/Culvert Groups"]
    results_hdf = _with_mesh(
        _geometry_file(tmp_path / "MODEL.p05.hdf", complete=True), CENTRES
    )

    geometry.graft_missing(incomplete, results_hdf)

    assert geometry.missing_tables(incomplete) == ()
    with h5py.File(incomplete, "r") as handle:
        # not just the two leaves: the attributes describing the barrels too
        assert f"{BARRELS}/Attributes" in handle


def test_graft_translates_face_indexes_it_copies(tmp_path: Path):
    """A face index copied without translating points at a different edge.

    The delivered geometry and the results file agree on face points and
    disagree on faces -- 10678 of 12868 sit at a different index. The boundary
    condition's External Faces is indexed by face, so it has to be rewritten in
    the receiving file's numbering, matched through coordinates.
    """
    from q50depth import geometry

    # Same two edges, listed the other way round.
    incomplete = _with_mesh(
        _geometry_file(tmp_path / "MODEL.g03.hdf", complete=False),
        CENTRES,
        faces=((1, 2), (0, 1)),
    )
    results_hdf = _with_mesh(
        _geometry_file(tmp_path / "MODEL.p05.hdf", complete=True),
        CENTRES,
        faces=((0, 1), (1, 2)),
    )

    geometry.graft_missing(incomplete, results_hdf)

    with h5py.File(incomplete, "r") as handle:
        copied = handle["Geometry/Boundary Condition Lines/External Faces"][...]
    # face 1 in the results file is edge (1,2), which is face 0 here; and 0 -> 1
    assert copied["Face Index"].tolist() == [0, 1]


def test_graft_refuses_a_mesh_it_does_not_recognise(tmp_path: Path):
    """Copied datasets are indexed by cell, so the cells have to be the same."""
    from q50depth import geometry

    incomplete = _with_mesh(
        _geometry_file(tmp_path / "MODEL.g03.hdf", complete=False), CENTRES
    )
    moved = _with_mesh(
        _geometry_file(tmp_path / "MODEL.p05.hdf", complete=True),
        [[0.0, 0.0], [1.0, 0.0], [99.0, 0.0]],
    )
    with pytest.raises(ComputeError, match="cell centres differ"):
        geometry.graft_missing(incomplete, moved)

    fewer = _with_mesh(
        _geometry_file(tmp_path / "other.p05.hdf", complete=True), CENTRES[:2]
    )
    with pytest.raises(ComputeError, match="cells in MODEL.g03.hdf"):
        geometry.graft_missing(incomplete, fewer)


def test_graft_on_a_complete_geometry_changes_nothing(tmp_path: Path):
    from q50depth import geometry

    complete = _with_mesh(
        _geometry_file(tmp_path / "MODEL.g03.hdf", complete=True), CENTRES
    )
    before = complete.read_bytes()
    assert geometry.graft_missing(complete, complete).added == ()
    assert complete.read_bytes() == before


def test_rebuild_refuses_when_the_results_file_is_no_better(tmp_path: Path):
    from q50depth import geometry

    incomplete = _geometry_file(tmp_path / "MODEL.g03.hdf", complete=False)
    also_incomplete = _geometry_file(tmp_path / "MODEL.p05.hdf", complete=False)
    with pytest.raises(ComputeError, match="does not carry a complete geometry"):
        geometry.rebuild_from_results(incomplete, also_incomplete)


def test_hecras_geometry_tool_is_reported_missing_not_guessed(tmp_path: Path):
    """Without RasProcess.exe the caller must fall back, not pretend it ran."""
    from q50depth import geometry

    ran, detail = geometry.complete_with_hecras(
        tmp_path / "MODEL.g03.hdf", None, tmp_path
    )
    assert ran is False
    assert "RasProcess.exe" in detail


def test_terrain_timestamp_is_set_from_the_geometry(tmp_path: Path):
    import os
    from datetime import datetime

    from q50depth import geometry

    terrain = tmp_path / "merge.Clone.hdf"
    terrain.write_bytes(b"terrain")
    (tmp_path / "merge.Clone.vrt").write_bytes(b"vrt")
    geometry_hdf = tmp_path / "MODEL.g03.hdf"
    with h5py.File(geometry_hdf, "w") as handle:
        group = handle.create_group("Geometry")
        group.attrs["Terrain Filename"] = np.bytes_(b".\\merge.Clone.hdf")
        group.attrs["Terrain File Date"] = np.bytes_(b"10JUN2026 17:49:26")

    applied = geometry.align_terrain_timestamp(geometry_hdf, tmp_path)
    assert applied == "10JUN2026 17:49:26"
    expected = datetime(2026, 6, 10, 17, 49, 26).timestamp()
    assert os.path.getmtime(terrain) == pytest.approx(expected, abs=1)
    assert os.path.getmtime(tmp_path / "merge.Clone.vrt") == pytest.approx(expected, abs=1)


def test_terrain_alignment_is_skipped_when_nothing_is_recorded(tmp_path: Path):
    from q50depth import geometry

    geometry_hdf = tmp_path / "MODEL.g03.hdf"
    with h5py.File(geometry_hdf, "w") as handle:
        handle.create_group("Geometry")
    assert geometry.align_terrain_timestamp(geometry_hdf, tmp_path) is None
