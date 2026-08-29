"""Synthetic fixtures.

The real data set is ~500 MB of client data and is not in this repository, so
the trap it contains is reproduced here in miniature: a project listing seven
plans, of which p04 is Q500 and p05 is Q50, plus a stray ``Backup.p01`` on
disk whose title is an exact Q50 match but which the project does not list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PLANS = {
    "p01": ("A_A_B_INPNAR_STEADY", "A_A_B_INPINAR_STEADY", "g01", "f01"),
    "p02": ("A_A_B_INPINAR_STEADY", "A_A_B_INPINAR", "g01", "f01"),
    "p03": ("A_A_B_INPINAR_UNSTEADY_2D", "INPINAR_Q500_UNSTEADY", "g03", "u01"),
    "p04": ("A_A_B_INPINAR_Q500", "A_A_B_INPINAR_Q500", "g03", "u04"),
    "p05": ("A_A_B_INPINAR_Q50", "Q50", "g03", "u05"),
    "p06": ("A_A_B_INPINAR_Q100", "Q100", "g03", "u06"),
    "p07": ("A_A_B_INPINAR_Q1000", "Q1000", "g03", "u08"),
}


def write_plan(folder: Path, stem: str, number: str, title: str, short_id: str,
               geom: str, flow: str) -> Path:
    path = folder / f"{stem}.{number}"
    # Short Identifier is a fixed width field in HEC-RAS; the padding matters
    # because a naive parser keeps the trailing spaces.
    path.write_text(
        f"Plan Title={title}\n"
        f"Program Version=6.60\n"
        f"Short Identifier={short_id:<40}\n"
        f"Simulation Date=02MAY2025,01:00,02MAY2025,02:10\n"
        f"Geom File={geom}\n"
        f"Flow File={flow}\n",
        encoding="latin-1",
    )
    return path


@pytest.fixture
def case_project(tmp_path: Path) -> Path:
    """A project folder shaped like the delivered one. Returns the folder."""
    folder = tmp_path / "1_Modeller"
    folder.mkdir(parents=True)
    stem = "A_A_B_INPINAR"

    lines = ["Proj Title=A_A_B_INPINAR", "Current Plan=p05", "SI Units"]
    lines += [f"Geom File={g}" for g in ("g01", "g02", "g03")]
    # the project lists plans out of order, exactly as the real one does
    lines += [f"Plan File={n}" for n in ("p03", "p02", "p01", "p04", "p05", "p06", "p07")]
    (folder / f"{stem}.prj").write_text("\n".join(lines) + "\n", encoding="latin-1")

    for number, (title, short_id, geom, flow) in PLANS.items():
        write_plan(folder, stem, number, title, short_id, geom, flow)

    # The trap: a stray plan file that is an exact Q50 match but is not listed
    # in the project file.
    write_plan(folder, "Backup", "p01", "A_A_B_INPINAR_Q50", "Q50", "g03", "u05")

    # Coordinate system files that share the .prj extension.
    for name in ("akarcay_prj.prj", "bank_lines.prj", "bank_v01.prj"):
        (folder / name).write_text(
            'PROJCS["WGS_1984_Transverse_Mercator",UNIT["Meters",1.0]]', encoding="latin-1"
        )
    return folder
