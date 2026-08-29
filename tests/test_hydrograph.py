"""Reading a boundary condition series out of a DSS text export.

The delivered flow files hold no hydrograph of their own; they point at a DSS
file. When HEC-RAS cannot read it, the unsteady engine crashes rather than
reporting a missing inflow, so the application can put the series into the
flow file instead and drop the dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from q50depth import hydrograph
from q50depth.errors import ComputeError

EXPORT = """\
/BASIN/GAUGE/DEBI/02MAY2025/5MIN/Q100/
RTS Ver: 1 Prog:DssVue LW:25JUN25 12:23:01 Tag:Tag Prec:27
Start: 02May2025 at 0100 hours;   End: 02May2025 at 0110 hours;  Number: 3
Units: M3/S    Type: INST-VAL
02MAY2025, 0100;   5.00
02MAY2025, 0105;   6.00
02MAY2025, 0110;   7.00
END DATA
/BASIN/GAUGE/DEBI/02MAY2025/5MIN/Q50/
RTS Ver: 1 Prog:DssVue LW:25JUN25 12:23:01 Tag:Tag Prec:27
Start: 02May2025 at 0100 hours;   End: 02May2025 at 0115 hours;  Number: 4
Units: M3/S    Type: INST-VAL
02MAY2025, 0100;   0.00
02MAY2025, 0105;   0.90
02MAY2025, 0110;   1.69
02MAY2025, 0114;   1.13
END DATA
"""


@pytest.fixture
def export(tmp_path: Path) -> Path:
    path = tmp_path / "debi.txt"
    path.write_text(EXPORT, encoding="latin-1")
    return path


def test_series_is_matched_across_different_spellings(export: Path):
    """The model says '5Minute' and '02May2025'; the export says '5MIN' and '02MAY2025'."""
    series = hydrograph.read_series(export, "/BASIN/GAUGE/DEBI/02May2025/5Minute/Q50/")
    assert series.values == (0.0, 0.9, 1.69, 1.13)
    assert series.interval_minutes == 5
    assert series.units.lower() == "m3/s"


def test_return_periods_are_not_confused(export: Path):
    """Q50 must not pick up Q100, and the block must stop at its own end."""
    assert hydrograph.read_series(export, "/BASIN/GAUGE/DEBI/x/5MIN/Q50/").values[0] == 0.0
    assert hydrograph.read_series(export, "/BASIN/GAUGE/DEBI/x/5MIN/Q100/").values[0] == 5.0


def test_hours_follow_the_declared_interval(export: Path):
    series = hydrograph.read_series(export, "/BASIN/GAUGE/DEBI/x/5MIN/Q50/")
    assert series.hours == pytest.approx((0.0, 5 / 60, 10 / 60, 15 / 60))
    assert series.peak == 1.69


def test_missing_series_is_refused(export: Path):
    with pytest.raises(ComputeError, match="no series matching"):
        hydrograph.read_series(export, "/BASIN/GAUGE/DEBI/x/5MIN/Q999/")


def test_ambiguous_series_is_refused(tmp_path: Path):
    path = tmp_path / "debi.txt"
    path.write_text(EXPORT + EXPORT, encoding="latin-1")
    with pytest.raises(ComputeError, match="4 series matching|2 series matching"):
        hydrograph.read_series(path, "/BASIN/GAUGE/DEBI/x/5MIN/Q50/")


def test_a_short_block_is_refused(tmp_path: Path):
    """The header declares how many ordinates there should be; trust it."""
    path = tmp_path / "debi.txt"
    path.write_text(EXPORT.replace("Number: 4", "Number: 9"), encoding="latin-1")
    with pytest.raises(ComputeError, match="declares 9 ordinates but 4"):
        hydrograph.read_series(path, "/BASIN/GAUGE/DEBI/x/5MIN/Q50/")


def test_unknown_interval_is_refused(tmp_path: Path):
    path = tmp_path / "debi.txt"
    path.write_text(EXPORT.replace("5MIN", "3MIN"), encoding="latin-1")
    with pytest.raises(ComputeError, match="Cannot tell the time step"):
        hydrograph.read_series(path, "/BASIN/GAUGE/DEBI/x/3MIN/Q50/")


def test_dss_pathname_is_read_from_the_flow_file(tmp_path: Path):
    flow = tmp_path / "MODEL.u05"
    flow.write_text(
        "Flow Title=Q50\nFlow Hydrograph= 0 \n"
        "DSS File=.\\_CBS\\d\\debi.dss\n"
        "DSS Path=/BASIN/GAUGE/DEBI/02May2025/5Minute/Q50/\nUse DSS=True\n",
        encoding="latin-1",
    )
    assert hydrograph.dss_pathname(flow) == "/BASIN/GAUGE/DEBI/02May2025/5Minute/Q50/"
    assert hydrograph.dss_pathname(tmp_path / "absent.u05") is None


def test_text_export_is_found_anywhere_in_the_project(tmp_path: Path):
    project = tmp_path / "1_Modeller"
    (project / "_CBS" / "d").mkdir(parents=True)
    (project / "2_CBS" / "d").mkdir(parents=True)
    dss = project / "_CBS" / "d" / "debi.dss"
    dss.write_bytes(b"copy")
    real = project / "2_CBS" / "d" / "debi.txt"
    real.write_text(EXPORT, encoding="latin-1")
    assert hydrograph.find_text_export(dss, project) == real
