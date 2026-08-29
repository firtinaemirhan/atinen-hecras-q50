"""Broken file references in the delivered project, and repairing the copy.

The real data set ships its inflow hydrograph in a DSS file, and the model
points at it with a path that does not resolve: ``.\\_CBS\\...`` while the
folder on disk is ``2_CBS``. HEC-RAS cannot load the plan, and writes a
truncated results file instead of failing loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from q50depth import references
from q50depth.errors import ComputeError


@pytest.fixture
def broken_project(tmp_path: Path) -> tuple[Path, Path]:
    """A project whose flow file points at a DSS folder that was renamed."""
    folder = tmp_path / "1_Modeller"
    folder.mkdir()
    plan = folder / "MODEL.p05"
    plan.write_text(
        "Plan Title=MODEL_Q50\nGeom File=g03\nFlow File=u05\n"
        "DSS File=.\\Q50\\Q50.dss\n",
        encoding="latin-1",
    )
    (folder / "MODEL.u05").write_text(
        "Flow Title=Q50\n"
        "Boundary Location=,,,,,mesh,,inflow,\n"
        "Flow Hydrograph= 0 \n"
        "DSS File=.\\_CBS\\debiler\\debi.dss\n"
        "DSS Path=/MODEL/GAUGE/FLOW/02May2025/5Minute/Q50/\n"
        "Use DSS=True\n",
        encoding="latin-1",
    )
    real = folder / "2_CBS" / "debiler"
    real.mkdir(parents=True)
    (real / "debi.dss").write_bytes(b"pretend DSS payload")
    return folder, plan


def test_collect_separates_inflow_from_output(broken_project):
    folder, plan = broken_project
    found = references.collect(folder, plan, "u05")
    assert [(r.kind, r.declared_in) for r in found] == [
        ("inflow", "MODEL.u05"),
        ("output", "MODEL.p05"),
    ]
    assert all(not r.exists for r in found)


def test_repair_puts_the_inflow_file_where_the_model_looks(broken_project):
    folder, plan = broken_project
    found = references.collect(folder, plan, "u05")
    done = references.repair(folder, found)

    inflow = folder / "_CBS" / "debiler" / "debi.dss"
    assert inflow.is_file()
    assert inflow.read_bytes() == b"pretend DSS payload"
    assert (folder / "2_CBS" / "debiler" / "debi.dss").is_file(), "original left in place"
    assert any(r.action == "copied into place" for r in done)


def test_repair_creates_the_output_folder_but_not_the_file(broken_project):
    folder, plan = broken_project
    references.repair(folder, references.collect(folder, plan, "u05"))
    assert (folder / "Q50").is_dir()
    assert not (folder / "Q50" / "Q50.dss").exists(), "HEC-RAS writes this itself"


def test_everything_resolves_after_repair(broken_project):
    folder, plan = broken_project
    references.repair(folder, references.collect(folder, plan, "u05"))
    after = references.collect(folder, plan, "u05")
    assert [r.exists for r in after if r.kind == "inflow"] == [True]


def test_repair_is_a_no_op_on_a_second_run(broken_project):
    """Re-running must not report work it did not do."""
    folder, plan = broken_project
    first = references.repair(folder, references.collect(folder, plan, "u05"))
    assert len(first) == 2
    assert references.repair(folder, references.collect(folder, plan, "u05")) == []


def test_missing_inflow_file_is_refused(broken_project):
    folder, plan = broken_project
    (folder / "2_CBS" / "debiler" / "debi.dss").unlink()
    with pytest.raises(ComputeError, match="no file named 'debi.dss'"):
        references.repair(folder, references.collect(folder, plan, "u05"))


def test_ambiguous_inflow_file_is_refused(broken_project):
    folder, plan = broken_project
    other = folder / "3_CBS" / "debiler"
    other.mkdir(parents=True)
    (other / "debi.dss").write_bytes(b"a different one")
    with pytest.raises(ComputeError, match="2 files share that name"):
        references.repair(folder, references.collect(folder, plan, "u05"))
