"""Run the HEC-RAS computation on Windows and keep the evidence, whatever happens.

The delivered model does not compute as it stands: the unsteady engine dies
with ``forrtl: severe (157) access violation`` inside ``READ_UN_HDF_STRUC``.
There is more than one credible reason for that, and they are not
distinguishable without running.  So this script does not argue: it runs the
candidates one after another, keeps everything each one wrote, and stops at
the first that produces a complete results file.

Every attempt leaves behind, under ``--evidence``:

    NN-<name>.log            everything the application printed
    NN-<name>.compute.txt    HEC-RAS's own computation log, read back out of
                             the plan HDF (this is what the GUI shows in its
                             computation window)
    NN-<name>.bco.txt        the .bco run log, when HEC-RAS wrote one
    NN-<name>.geometry-before.txt   what the geometry declared going in
    NN-<name>.geometry-after.txt    and what it declared coming out

That is the point of the script.  A run that fails and explains why is worth
more than one that succeeds and cannot be shown.

Only files HEC-RAS wrote *during that attempt* are kept, and each one carries a
header naming its source, size and modification time.  The working copy is a
copy of the delivered project, and the delivered project already contains a
results file from the client's own successful run in July -- an earlier version
of this script read it whenever an attempt failed before HEC-RAS wrote anything,
and saved the client's July log under a filename claiming to be that attempt.
An attempt that produced no log now says exactly that.

    python tools\\windows_verify.py ^
        --project "C:\\path\\to\\CASE_DATA 2" ^
        --ras-dir "C:\\Program Files (x86)\\HEC\\HEC-RAS\\6.6" ^
        --reference "C:\\path\\to\\CASE_DATA 2\\AKA_AFY_BAY_INPINAR_1\\3_Pafta\\6_derinlik\\q50_d.tif"
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Attempt:
    name: str
    why: str
    arguments: list[str] = field(default_factory=list)


#: In order of how well each is supported by what the data actually shows.
ATTEMPTS = [
    Attempt(
        "graft",
        "The delivered geometry is missing four things the delivered results "
        "have: GeomPreprocess, the two datasets saying which mesh cell each "
        "culvert barrel opens into, and the boundary condition lines' External "
        "Faces. Copy exactly those four and leave the rest of the geometry "
        "alone. Face indexes are translated through coordinates, because the "
        "two files number faces differently.",
        ["--geometry", "graft", "--ib-tables", "rebuild"],
    ),
    Attempt(
        "harvest",
        "Replace the whole geometry with the one inside the delivered results, "
        "which is complete by definition -- it produced the results. The open "
        "question is whether HEC-RAS keeps it: the run starts by writing the "
        "geometry from the text .g03, and that may throw the transplant away. "
        "The geometry-before and geometry-after files now answer that.",
        ["--geometry", "harvest", "--ib-tables", "rebuild"],
    ),
    Attempt(
        "graft-single-core",
        "The same repair on one core. A parallel solver can fail where a serial "
        "one does not, and this has not been tried since the repair started "
        "working.",
        ["--geometry", "graft", "--ib-tables", "rebuild", "--cores", "1"],
    ),
    Attempt(
        "graft-inline-hydrograph",
        "The same repair, with the inflow hydrograph written into the flow "
        "file so the run does not depend on HEC-RAS opening the DSS at all. "
        "Worth trying because a dialog saying 'Error in Loading Plan Data' "
        "still appears even with the DSS in place.",
        ["--geometry", "graft", "--ib-tables", "rebuild", "--inflow", "inline"],
    ),
    Attempt(
        "graft-controller",
        "The same repair, driven through the COM automation object the GUI "
        "uses instead of the command line runner.",
        ["--geometry", "graft", "--ib-tables", "rebuild", "--runner", "controller"],
    ),
    Attempt(
        "compute-geometry",
        "RAS Mapper's own geometry-completion pipeline. Last on the list and "
        "suspected of doing harm: on 2026-09-02 it grew the geometry from "
        "769 KB to 2.4 MB, wrote none of the four missing datasets, returned "
        "success=False with no error, and a geometry measured afterwards "
        "declared one SA/2D connection where the delivered file declares two. "
        "Kept so that claim can be tested rather than repeated -- the "
        "geometry-before and geometry-after files settle it.",
        ["--geometry", "compute", "--ib-tables", "rebuild"],
    ),
]


def _compute_messages(plan_hdf: Path) -> str:
    """HEC-RAS's computation log, which it stores inside the results file."""
    try:
        import h5py  # noqa: PLC0415
    except ImportError:
        return "(h5py not available)"
    if not plan_hdf.is_file():
        return "(no results file was written)"
    keys = (
        "Results/Summary/Compute Messages (text)",
        "Results/Unsteady/Summary/Compute Messages (text)",
        "Results/Summary/Compute Messages",
    )
    try:
        with h5py.File(plan_hdf, "r") as handle:
            for key in keys:
                if key not in handle:
                    continue
                raw = handle[key][()]
                if isinstance(raw, bytes):
                    return raw.decode("latin-1", errors="replace")
                parts = raw.tolist() if hasattr(raw, "tolist") else [raw]
                if isinstance(parts, bytes):
                    return parts.decode("latin-1", errors="replace")
                return "\n".join(
                    p.decode("latin-1", errors="replace") if isinstance(p, bytes) else str(p)
                    for p in parts
                )
    except OSError as exc:
        return f"(results file could not be opened: {exc})"
    return "(the results file carries no computation log)"


#: A file only counts as this attempt's evidence if it was written after the
#: attempt started. Without that test the workspace hands back the client's own
#: results file -- the working copy is a copy of the delivered project, and the
#: delivered project already contains a computed p05.hdf from their July run.
#: Reading it produced a "02-rasprocess.compute.txt" that was byte for byte the
#: client's 09Jul2026 log, under a filename claiming to be tonight's attempt.
#: Evidence that could not be produced must say so; it must not be filled in
#: with older evidence.
_CLOCK_SLACK_SECONDS = 5.0


def _written_since(path: Path, started_at: float) -> bool:
    try:
        return path.stat().st_mtime >= started_at - _CLOCK_SLACK_SECONDS
    except OSError:
        return False


def _provenance(path: Path) -> str:
    stat = path.stat()
    when = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    return f"# source: {path}\n# modified: {when}\n# bytes: {stat.st_size}\n\n"


#: What the geometry looks like, in the few terms that have decided every step
#: of this investigation. Written before and after each attempt, because more
#: than one hour has gone into arguing about a file when the disagreement was
#: about *which* file: the delivered geometry declares two SA/2D connections
#: and two boundary condition lines, and a copy that has been through RAS
#: Mapper's completion pipeline may not.
def _geometry_state(path: Path) -> str:
    try:
        import h5py  # noqa: PLC0415
        import numpy as np  # noqa: F401, PLC0415
    except ImportError:
        return "(h5py not available)"
    if not path.is_file():
        return f"{path}: not present"

    lines = [f"{path}", f"  bytes: {path.stat().st_size}"]
    try:
        with h5py.File(path, "r") as handle:
            structures = handle.get("Geometry/Structures/Attributes")
            if structures is None:
                lines.append("  structures: none")
            else:
                data = structures[...]
                names = data.dtype.names or ()
                lines.append(f"  structures: {len(data)}")
                for field in ("Connection", "Mode", "Culvert Groups"):
                    if field in names:
                        values = [
                            v.decode("latin-1").strip() if isinstance(v, bytes) else v
                            for v in data[field]
                        ]
                        lines.append(f"    {field}: {values}")
            bc = handle.get("Geometry/Boundary Condition Lines")
            lines.append(
                f"  boundary condition lines: {sorted(bc.keys())}" if bc
                else "  boundary condition lines: GROUP ABSENT"
            )
            for key in (
                "Geometry/GeomPreprocess",
                "Geometry/Structures/Culvert Groups/Barrels/Upstream Cells",
                "Geometry/Structures/Culvert Groups/Barrels/Downstream Cells",
                "Geometry/Boundary Condition Lines/External Faces",
            ):
                lines.append(f"  {'present' if key in handle else 'ABSENT ':<8} {key}")
    except OSError as exc:
        lines.append(f"  could not be read: {exc}")
    return "\n".join(lines)


def _write_geometry_state(workspace: Path, evidence: Path, stem: str, when: str) -> None:
    folders = [p for p in workspace.glob("*") if p.is_dir()] or [workspace]
    blocks = [
        _geometry_state(path)
        for folder in folders
        for path in sorted(folder.glob("*.g*.hdf"))
    ]
    (evidence / f"{stem}.geometry-{when}.txt").write_text(
        f"# geometry {when} this attempt\n\n"
        + ("\n\n".join(blocks) if blocks else "(no geometry HDF in the workspace)")
        + "\n",
        encoding="utf-8",
    )


def _collect(workspace: Path, evidence: Path, stem: str, started_at: float) -> None:
    """Keep what HEC-RAS wrote *during this attempt*, and nothing else.

    Every file kept carries a header naming where it came from and when it was
    written, so a log can never be read as belonging to a run that did not
    produce it.
    """
    folders = [p for p in workspace.glob("*") if p.is_dir()] or [workspace]

    fresh_plan = next(
        (
            plan_hdf
            for folder in folders
            for plan_hdf in sorted(folder.glob("*.p*.hdf"))
            if _written_since(plan_hdf, started_at)
        ),
        None,
    )
    compute_path = evidence / f"{stem}.compute.txt"
    if fresh_plan is None:
        stale = [
            str(plan_hdf)
            for folder in folders
            for plan_hdf in sorted(folder.glob("*.p*.hdf"))
        ]
        compute_path.write_text(
            "# HEC-RAS produced no results file during this attempt.\n"
            "# It stopped before writing one, so there is no computation log\n"
            "# for this attempt. The application's own output is in "
            f"{stem}.log.\n"
            + (
                "# Plan HDF files that were already in the working copy and are\n"
                "# NOT this attempt's output:\n"
                + "".join(f"#   {path}\n" for path in stale)
                if stale
                else ""
            ),
            encoding="utf-8",
        )
    else:
        compute_path.write_text(
            _provenance(fresh_plan) + _compute_messages(fresh_plan), encoding="utf-8"
        )

    fresh_bco = next(
        (
            bco
            for folder in folders
            for bco in sorted(folder.glob("*.bco*"))
            if _written_since(bco, started_at)
        ),
        None,
    )
    bco_path = evidence / f"{stem}.bco.txt"
    if fresh_bco is None:
        bco_path.write_text(
            "# No .bco run log was written during this attempt.\n", encoding="utf-8"
        )
    else:
        bco_path.write_text(
            _provenance(fresh_bco)
            + fresh_bco.read_text(encoding="latin-1", errors="replace"),
            encoding="utf-8",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", type=Path, required=True,
                        help="The delivered data folder (CASE DATA 2). Never modified.")
    parser.add_argument("--ras-dir", type=Path, required=True,
                        help=r'HEC-RAS installation, e.g. "C:\Program Files (x86)\HEC\HEC-RAS\6.6"')
    parser.add_argument("--reference", type=Path,
                        help="The client's q50_d.tif, to measure the result against.")
    parser.add_argument("--evidence", type=Path, default=ROOT / "evidence",
                        help="Where to keep the logs (default: ./evidence).")
    parser.add_argument("--workspace", type=Path, default=Path.home() / "q50-workspace",
                        help="Where the project is copied before computing.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Where the raster goes. Default: <evidence>/q50_depth.tif, "
                             "which keeps runs from rewriting a tracked file and "
                             "blocking git pull on the machine doing the running.")
    parser.add_argument("--only", metavar="NAME",
                        help="Run just one attempt by name, instead of all of them.")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="Seconds to allow each attempt (default: 1800). The "
                             "client's own successful run took 1 min 35 s, so an "
                             "attempt still going after half an hour is stuck, not "
                             "slow -- and a stuck attempt costs more than a "
                             "cancelled one.")
    args = parser.parse_args(argv)

    if platform.system() != "Windows":
        print("This script only does anything on Windows: HEC-RAS runs nowhere else.")
        print(f"Detected {platform.system()}. Nothing was run.")
        return 2

    args.evidence.mkdir(parents=True, exist_ok=True)
    if args.output is None:
        args.output = args.evidence / "q50_depth.tif"

    # HEC-RAS raises modal dialogs on a headless or COM launch. ras-commander can
    # dismiss them, but only with pywin32; without it a run does not fail, it
    # *hangs* with an invisible window open, which is far harder to read than a
    # crash. One attempt sat for 11 minutes that way on 2026-09-02.
    try:
        import win32gui  # noqa: F401, PLC0415
        print("pywin32   present; ras-commander can dismiss HEC-RAS dialogs")
    except ImportError:
        print("pywin32   MISSING. HEC-RAS dialogs cannot be dismissed and an "
              "attempt may hang instead of failing.")
        print("          pip install -r requirements-windows.txt")
    attempts = ATTEMPTS
    if args.only:
        attempts = [a for a in ATTEMPTS if a.name == args.only]
        if not attempts:
            parser.error(f"no attempt named {args.only!r}; "
                         f"choose from {', '.join(a.name for a in ATTEMPTS)}")

    print("=" * 72)
    print(f"python      {sys.version.split()[0]}")
    print(f"platform    {platform.platform()}")
    print(f"HEC-RAS     {args.ras_dir}")
    try:
        import ras_commander  # noqa: PLC0415
        print(f"ras-commander {getattr(ras_commander, '__version__', 'installed')}")
    except ImportError:
        print("ras-commander NOT INSTALLED -- run: pip install -r requirements-windows.txt")
        return 2
    print("=" * 72)

    summary: list[tuple[str, str]] = []
    for index, attempt in enumerate(attempts, start=1):
        stem = f"{index:02d}-{attempt.name}"
        print()
        print("-" * 72)
        print(f"[{index}/{len(attempts)}] {attempt.name}")
        for line in attempt.why.split(". "):
            if line.strip():
                print(f"    {line.strip().rstrip('.')}.")
        print("-" * 72)

        command = [
            sys.executable, str(ROOT / "main.py"),
            "--project", str(args.project),
            "--ras-dir", str(args.ras_dir),
            "--workspace", str(args.workspace),
            "--overwrite-workspace",
            "--output", str(args.output),
            "--integrity", "off",
            *attempt.arguments,
        ]
        print("  " + " ".join(f'"{c}"' if " " in c else c for c in command))
        # Anything older than this instant belongs to an earlier run, or to the
        # client, and is not this attempt's evidence.
        started_at = time.time()
        if args.workspace.exists():
            _write_geometry_state(args.workspace, args.evidence, stem, "before")
        try:
            finished = subprocess.run(
                command, capture_output=True, text=True, timeout=args.timeout, cwd=str(ROOT)
            )
            transcript = (finished.stdout or "") + "\n" + (finished.stderr or "")
            code = finished.returncode
        except subprocess.TimeoutExpired:
            transcript = f"(timed out after {args.timeout} s)"
            code = 124

        (args.evidence / f"{stem}.log").write_text(transcript, encoding="utf-8")
        _collect(args.workspace, args.evidence, stem, started_at)
        if args.workspace.exists():
            _write_geometry_state(args.workspace, args.evidence, stem, "after")

        tail = [line for line in transcript.splitlines() if line.strip()][-12:]
        for line in tail:
            print(f"  | {line}")

        if code == 0:
            print()
            print(f"  SUCCEEDED. Evidence in {args.evidence}\\{stem}.*")
            summary.append((attempt.name, "succeeded"))
            break
        print()
        print(f"  failed (exit {code}). Evidence in {args.evidence}\\{stem}.*")
        summary.append((attempt.name, f"failed (exit {code})"))

    print()
    print("=" * 72)
    for name, outcome in summary:
        print(f"  {name:<20} {outcome}")
    print("=" * 72)

    succeeded = summary and summary[-1][1] == "succeeded"
    if not succeeded:
        print()
        print("Nothing computed. Send the whole evidence folder back; the "
              "computation logs say which routine HEC-RAS died in, and that "
              "is what decides the next step.")
        return 1

    print()
    print(f"The raster HEC-RAS's own results produced: {args.output}")
    if args.reference is not None and args.reference.is_file():
        print()
        print("Measuring it against the client's map:")
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "compare_reference.py"),
             str(args.output), str(args.reference),
             "--png", str(args.evidence / "comparison.png")],
            cwd=str(ROOT),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
