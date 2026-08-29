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
    text = prj.read_text(encoding="latin-1")
    assert "Geom File=g03" in text and "Geom File=g01" not in text
    assert "Unsteady File=u05" in text and "Unsteady File=u06" not in text
    assert "Y Axis Title=Elevation" in text, "unrelated settings are kept"


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
