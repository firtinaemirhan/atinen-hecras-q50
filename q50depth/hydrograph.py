"""Read a boundary condition time series out of a DSS text export.

The delivered flow files carry no hydrograph of their own::

    Flow Hydrograph= 0
    DSS File=.\\_CBS\\akarcay_debiler\\akarcay_debi.dss
    DSS Path=/AKA_AFY_BAY_INPINAR_1/AKC_126_YM/DEBI/02May2025/5Minute/Q50/
    Use DSS=True

so every run depends on HEC-RAS opening that DSS file. When it cannot, the
unsteady engine has no inflow to read and dies with an access violation
instead of a message.

The delivery also ships ``akarcay_debi.txt``, a DssVue text export of the same
file. This module reads the series out of it, which lets the application write
the hydrograph straight into the working copy's flow file and drop the DSS
dependency altogether.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import ComputeError

_ENCODING = "latin-1"
_HEADER = re.compile(
    r"Start:\s*(?P<start>.+?)\s*;\s*End:\s*(?P<end>.+?)\s*;\s*Number:\s*(?P<count>\d+)",
    re.IGNORECASE,
)
_UNITS = re.compile(r"Units:\s*(?P<units>\S+)\s+Type:\s*(?P<type>\S+)", re.IGNORECASE)
_VALUE = re.compile(r"^\s*(\d{2}\w{3}\d{4})\s*,\s*(\d{4})\s*;\s*(-?[\d.]+)\s*$")

# DSS writes the E part as "5Minute" in models and "5MIN" in exports.
_INTERVALS = {
    "1MIN": 1, "1MINUTE": 1,
    "5MIN": 5, "5MINUTE": 5,
    "10MIN": 10, "10MINUTE": 10,
    "15MIN": 15, "15MINUTE": 15,
    "30MIN": 30, "30MINUTE": 30,
    "1HOUR": 60, "1HR": 60,
    "6HOUR": 360, "1DAY": 1440,
}


@dataclass(frozen=True)
class Series:
    """One time series, as the model's boundary condition expects it."""

    pathname: str
    source: Path
    interval_minutes: int
    units: str
    values: tuple[float, ...]

    @property
    def hours(self) -> tuple[float, ...]:
        step = self.interval_minutes / 60.0
        return tuple(index * step for index in range(len(self.values)))

    @property
    def peak(self) -> float:
        return max(self.values) if self.values else 0.0

    def summary(self) -> str:
        return (
            f"{len(self.values)} ordinates at {self.interval_minutes} min, "
            f"peak {self.peak:g} {self.units.lower()}"
        )


def _parts(pathname: str) -> tuple[str, ...]:
    """Split a DSS pathname into its A..F parts, upper-cased."""
    return tuple(part.strip().upper() for part in pathname.strip("/").split("/"))


def _same_series(wanted: str, candidate: str) -> bool:
    """Compare two DSS pathnames on the parts that identify the series.

    The D part is a date block and the E part is spelled differently between a
    model file and an export, so only A, B, C and F are compared.
    """
    a, b = _parts(wanted), _parts(candidate)
    if len(a) < 6 or len(b) < 6:
        return False
    return (a[0], a[1], a[2], a[5]) == (b[0], b[1], b[2], b[5])


def _interval_from(pathname: str) -> int | None:
    parts = _parts(pathname)
    if len(parts) < 5:
        return None
    return _INTERVALS.get(parts[4].replace(" ", ""))


def dss_pathname(flow_path: Path) -> str | None:
    """The ``DSS Path=`` a flow file reads its boundary condition from."""
    if not flow_path.is_file():
        return None
    match = re.search(
        r"^DSS Path=(.+?)\s*$", flow_path.read_text(encoding=_ENCODING), re.MULTILINE
    )
    return match.group(1) if match else None


def find_text_export(dss_file: Path, project_folder: Path) -> Path | None:
    """The DssVue text export of a DSS file, wherever it sits in the project.

    It normally lies next to the DSS file, but the application copies the DSS
    into the location the model expects and leaves the export where it was, so
    the whole project is searched by name as well.
    """
    sibling = dss_file.with_suffix(".txt")
    if sibling.is_file():
        return sibling
    matches = [p for p in project_folder.rglob(sibling.name) if p.is_file()]
    return matches[0] if len(matches) == 1 else None


def embed(flow_path: Path, series: Series) -> None:
    """Write ``series`` into the flow file as an inline hydrograph.

    The HEC-RAS fixed-width table format is not written here: that is
    ``ras-commander``'s ``set_boundary_inline_hydrograph``, which also clears
    ``Use DSS``, removes the ``DSS File``/``DSS Path`` lines and fixes up the
    ``Interval`` line and the ordinate count.
    """
    try:
        import pandas as pd  # noqa: PLC0415
        from ras_commander import RasUnsteady  # noqa: PLC0415
    except ImportError as exc:
        raise ComputeError(
            "Embedding the inflow needs ras-commander (and pandas).",
            hint="On the Windows machine: pip install -r requirements-windows.txt",
        ) from exc

    frame = pd.DataFrame({"hour": list(series.hours), "value": list(series.values)})
    updated = RasUnsteady.set_boundary_inline_hydrograph(
        str(flow_path), frame, bc_type="Flow Hydrograph"
    )
    if not updated:
        raise ComputeError(
            f"No 'Flow Hydrograph' boundary condition was found in {flow_path.name}.",
            hint="The inflow cannot be embedded; leave --inflow at dss.",
        )


def read_series(export: Path, pathname: str) -> Series:
    """Pull one series out of a DssVue text export.

    The export is a flat list of blocks: a pathname line, three header lines,
    then ``DATE, TIME;  VALUE`` rows until ``END DATA``.
    """
    lines = export.read_text(encoding=_ENCODING).splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("/") and line.rstrip().endswith("/")]

    matches = [i for i in starts if _same_series(pathname, lines[i])]
    if not matches:
        raise ComputeError(
            f"{export.name} has no series matching {pathname}.",
            hint="The text export does not cover this scenario, so the inflow "
            "cannot be embedded; the model has to read the DSS file itself.",
        )
    if len(matches) > 1:
        found = ", ".join(lines[i].strip() for i in matches[:4])
        raise ComputeError(
            f"{export.name} has {len(matches)} series matching {pathname}: {found}",
            hint="Cannot tell which one the model means.",
        )

    index = matches[0]
    block: list[str] = []
    for line in lines[index + 1 :]:
        if line.strip() == "END DATA" or (line.startswith("/") and line.rstrip().endswith("/")):
            break
        block.append(line)

    units = "m3/s"
    units_match = next((_UNITS.search(line) for line in block if _UNITS.search(line)), None)
    if units_match:
        units = units_match.group("units")

    values = [float(m.group(3)) for m in (_VALUE.match(line) for line in block) if m]
    if not values:
        raise ComputeError(f"{export.name}: the block for {pathname} holds no values.")

    declared = next((_HEADER.search(line) for line in block if _HEADER.search(line)), None)
    if declared and int(declared.group("count")) != len(values):
        raise ComputeError(
            f"{export.name}: block for {pathname} declares "
            f"{declared.group('count')} ordinates but {len(values)} were read."
        )

    interval = _interval_from(lines[index]) or _interval_from(pathname)
    if interval is None:
        raise ComputeError(
            f"Cannot tell the time step of {pathname}.",
            hint="Its DSS E part is not one of the intervals this tool knows.",
        )

    return Series(
        pathname=lines[index].strip(),
        source=export,
        interval_minutes=interval,
        units=units,
        values=tuple(values),
    )
