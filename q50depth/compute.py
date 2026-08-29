"""Run a plan in HEC-RAS.

HEC-RAS is a Windows program, so this is the only part of the pipeline that
cannot run on the development machine.  It is kept behind one narrow function
so the rest of the application stays portable and testable.

Two back ends are offered, both provided by ``ras-commander`` (the library the
brief suggests), so no undocumented command line switches are invented:

``cmdr``
    ``RasCmdr.compute_plan`` -- runs the plan through the HEC-RAS command line
    runner.  Default.
``controller``
    ``RasControl.run_plan`` -- drives the ``RAS66.HECRASController`` COM
    automation object, i.e. the same interface the HEC-RAS GUI exposes.
    Useful when the command line runner refuses the model.

The API signatures used here were read off the installed ras-commander
package (0.99.x) rather than from memory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .errors import ComputeError

RUNNERS = ("cmdr", "controller")

# HEC-RAS creates the plan HDF when a run starts and fills it in as it goes.
# These are the groups a finished run leaves behind.
_COMPLETE = ("Plan Data/Plan Information", "Results")


def clear_stale_results(plan_hdf: Path) -> bool:
    """Remove a previous run's results from the working copy.

    A truncated HDF left behind by a failed run is worse than none: HEC-RAS
    reads it when the plan is opened, and the application would otherwise have
    to tell a fresh failure apart from an old one.
    """
    if plan_hdf.is_file():
        plan_hdf.unlink()
        return True
    return False


def _hdf_compute_messages(plan_hdf: Path) -> str:
    """HEC-RAS also stores its computation log inside the results file.

    A run that aborted usually still wrote this, which makes it the best
    account of what went wrong when no text log was produced.
    """
    if not plan_hdf.is_file():
        return ""
    try:
        import h5py  # noqa: PLC0415

        with h5py.File(plan_hdf, "r") as handle:
            for key in (
                "Results/Summary/Compute Messages (text)",
                "Results/Unsteady/Summary/Compute Messages (text)",
                "Results/Summary/Compute Messages",
            ):
                if key in handle:
                    raw = handle[key][()]
                    if isinstance(raw, bytes):
                        return raw.decode("latin-1", errors="replace")
                    if hasattr(raw, "tolist"):
                        parts = raw.tolist()
                        if isinstance(parts, bytes):
                            return parts.decode("latin-1", errors="replace")
                        return "\n".join(
                            p.decode("latin-1", errors="replace") if isinstance(p, bytes) else str(p)
                            for p in parts
                        )
    except (OSError, KeyError, ValueError):
        return ""
    return ""


def _log_tail(prj_path: Path, plan_number: str, lines: int = 40) -> str:
    """Whatever HEC-RAS wrote about this run, in order of usefulness.

    The detailed messages are the ones the GUI shows in its computation
    window. They live in a text file next to the plan, or -- when HEC-RAS did
    not get far enough to write one -- inside the results file. ``.bco`` is
    the last resort: it usually holds only the run banner.
    """
    short = plan_number.lstrip("pP")
    plan_path = prj_path.with_suffix(f".p{short}")
    plan_hdf = plan_path.with_name(plan_path.name + ".hdf")

    sources: list[tuple[str, str]] = []
    for candidate in (
        Path(f"{plan_path}.computeMsgs.txt"),
        Path(f"{plan_path}.comp_msgs.txt"),
    ):
        if candidate.is_file():
            try:
                sources.append((candidate.name, candidate.read_text("latin-1", errors="replace")))
            except OSError:
                pass

    messages = _hdf_compute_messages(plan_hdf)
    if messages.strip():
        sources.append((f"{plan_hdf.name} -> Compute Messages", messages))

    for candidate in (prj_path.with_suffix(f".bco{short}"), prj_path.with_suffix(f".b{short}")):
        if candidate.is_file():
            try:
                sources.append((candidate.name, candidate.read_text("latin-1", errors="replace")))
            except OSError:
                pass

    for name, text in sources:
        tail = [line.rstrip() for line in text.splitlines() if line.strip()][-lines:]
        if tail:
            body = "\n".join(f"    {line}" for line in tail)
            return f"\n  HEC-RAS wrote this in {name}:\n{body}"
    return ""


def verify_results(plan_hdf: Path, prj_path: Path, plan_number: str) -> None:
    """Confirm the run actually produced results, and say why if it did not.

    ras-commander reports success from the runner's exit status, which stays
    zero even when HEC-RAS aborts during loading and leaves a stub file.
    """
    if not plan_hdf.is_file():
        raise ComputeError(
            f"HEC-RAS finished without writing {plan_hdf.name}.",
            hint="The run never started." + _log_tail(prj_path, plan_number),
        )
    try:
        import h5py  # noqa: PLC0415

        with h5py.File(plan_hdf, "r") as handle:
            missing = [key for key in _COMPLETE if key not in handle]
    except OSError as exc:
        raise ComputeError(
            f"{plan_hdf.name} is not a readable HDF5 file after the run: {exc}",
            hint=_log_tail(prj_path, plan_number).strip() or None,
        ) from exc

    if missing:
        raise ComputeError(
            f"HEC-RAS left {plan_hdf.name} unfinished (no {', '.join(missing)}).",
            hint="The runner reported success, but the model did not compute. A "
            "dialog during loading, or a file the plan needs that does not "
            "resolve, is the usual cause." + _log_tail(prj_path, plan_number),
        )


@dataclass(frozen=True)
class ComputeOutcome:
    runner: str
    plan_number: str
    seconds: float
    detail: str


def _import_ras_commander():
    try:
        import ras_commander  # noqa: PLC0415  (optional, Windows-only dependency)
    except ImportError as exc:
        raise ComputeError(
            "ras-commander is not installed, so HEC-RAS cannot be driven from Python.",
            hint="On the Windows machine: pip install -r requirements-windows.txt. "
            "On macOS/Linux there is no HEC-RAS to drive; use --use-existing-results "
            "to work with results that were computed earlier.",
        ) from exc
    return ras_commander


def _resolve_ras_version(ras_dir: Path) -> str:
    """Turn ``--ras-dir`` into what ras-commander calls a ras_version.

    It accepts either a version string ("6.6") or a full path to ``Ras.exe``.
    A path is preferred: it also covers installations outside
    ``C:\\Program Files (x86)\\HEC\\HEC-RAS``.
    """
    ras_dir = Path(ras_dir).expanduser()
    if ras_dir.is_file():
        if ras_dir.suffix.lower() != ".exe":
            raise ComputeError(f"--ras-dir points at {ras_dir}, which is not an executable.")
        return str(ras_dir)
    executable = ras_dir / "Ras.exe"
    if not executable.is_file():
        raise ComputeError(
            f"No Ras.exe in {ras_dir}.",
            hint="Pass the HEC-RAS installation folder, for example "
            r'--ras-dir "C:\Program Files (x86)\HEC\HEC-RAS\6.6"',
        )
    return str(executable)


def run_plan(
    project_folder: Path,
    prj_path: Path,
    plan_number: str,
    ras_dir: Path,
    runner: str = "cmdr",
    cores: int | None = None,
) -> ComputeOutcome:
    """Compute one plan in place, inside ``project_folder``.

    ``project_folder`` is expected to be the working copy: this function
    deliberately does not guard the original data, because it never sees it.
    """
    if runner not in RUNNERS:
        raise ComputeError(f"Unknown runner {runner!r}; expected one of {', '.join(RUNNERS)}.")

    rc = _import_ras_commander()
    ras_version = _resolve_ras_version(ras_dir)
    short_number = plan_number.lstrip("pP")  # ras-commander addresses plans as "05"

    started = time.monotonic()
    try:
        project = rc.init_ras_project(str(project_folder), ras_version)
    except Exception as exc:
        raise ComputeError(
            f"HEC-RAS project {prj_path.name} could not be initialised: {exc}",
            hint="Check that HEC-RAS is installed at the path given by --ras-dir.",
        ) from exc

    try:
        if runner == "cmdr":
            outcome = rc.RasCmdr.compute_plan(
                short_number,
                ras_object=project,
                force_rerun=True,
                num_cores=cores,
            )
            succeeded = bool(getattr(outcome, "success", outcome))
            detail = f"RasCmdr.compute_plan -> success={succeeded}"
        else:
            outcome = rc.RasControl.run_plan(
                short_number,
                ras_object=project,
                force_recompute=True,
            )
            succeeded = bool(getattr(outcome, "success", outcome))
            detail = f"RasControl.run_plan -> success={succeeded}"
    except Exception as exc:
        raise ComputeError(
            f"HEC-RAS failed while computing plan {plan_number}: {exc}",
            hint="The HEC-RAS computation log in the project folder "
            f"({prj_path.stem}.bco*) usually says why.",
        ) from exc

    elapsed = time.monotonic() - started
    if not succeeded:
        raise ComputeError(
            f"HEC-RAS reported that plan {plan_number} did not compute successfully.",
            hint=f"See {prj_path.stem}.bco{short_number} in {project_folder}.",
        )
    return ComputeOutcome(runner, plan_number, elapsed, detail)
