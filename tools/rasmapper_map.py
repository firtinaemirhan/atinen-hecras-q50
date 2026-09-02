"""Have RASMapper itself draw the depth map, then measure ours against it.

Why this exists: the client's reference map went through a GIS step after
RASMapper produced it -- its grid no longer sits on the terrain's pixels, and
the raw RASMapper export that fed it is not in the delivery.  So the reference
answers "how close are we to the finished product", but it cannot answer "is
our water surface the one RASMapper draws".  Only RASMapper can answer that.

This tool asks it.  ``RasMap.store_all_maps`` drives RAS Mapper's own stored-map
generation, which is the same code path the modeller used, and it maps results
that already exist -- so it does not need the unsteady engine to run.  That
matters: the depth map can be checked against RASMapper even while the compute
is still failing.

Three rasters come out of a full run, and each comparison says something
different:

    RASMapper vs ours       is our water surface the one RASMapper draws?
    RASMapper vs reference  how much of the difference is the client's own
                            GIS post-processing, which we cannot reproduce?
    ours vs reference       the headline number, measured elsewhere too

Windows only: RAS Mapper is part of HEC-RAS.

    python tools\\rasmapper_map.py --project "C:\\...\\CASE DATA 2" ^
        --ras-dir "C:\\Program Files (x86)\\HEC\\HEC-RAS\\6.6" ^
        --reference "C:\\...\\3_Pafta\\6_derinlik\\q50_d.tif"
"""

from __future__ import annotations

import argparse
import inspect
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: Parameters this tool passes to RasMap.store_all_maps. The signature was read
#: off the installed package (0.99.1) rather than from documentation, but the
#: Windows machine may carry a different build -- so the names are checked
#: against the signature at run time instead of being assumed.
REQUIRED_PARAMETERS = (
    "plan_number",
    "mode",
    "depth",
    "profile",
    "render_mode",
    "terrain_name",
    "output_path",
    "ras_version",
)


def _check_signature(function) -> list[str]:
    """Which parameters this build of ras-commander does not accept."""
    accepted = inspect.signature(function).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in accepted.values()):
        return []
    return [name for name in REQUIRED_PARAMETERS if name not in accepted]


def _newest_depth_raster(folder: Path) -> Path | None:
    candidates = [
        p
        for p in folder.rglob("*.tif")
        if "depth" in p.name.lower() or "depth" in p.parent.name.lower()
    ]
    if not candidates:
        candidates = list(folder.rglob("*.tif"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", type=Path, required=True,
                        help="The delivered data folder. Copied first; never modified.")
    parser.add_argument("--ras-dir", type=Path, required=True,
                        help='HEC-RAS installation folder, or a full path to Ras.exe. '
                             r'e.g. "C:\Program Files (x86)\HEC\HEC-RAS\6.6"')
    parser.add_argument("--reference", type=Path,
                        help="The client's q50_d.tif, for the second comparison.")
    parser.add_argument("--ours", type=Path, default=ROOT / "OUTPUT" / "q50_depth.tif",
                        help="The raster this project produced.")
    parser.add_argument("--plan", default="05", help="Plan number (default: 05, the Q50 plan).")
    parser.add_argument("--render-mode", default="sloping",
                        help="Water surface RAS Mapper should draw (default: sloping, "
                             "which is what the project's own .rasmap specifies).")
    parser.add_argument("--workspace", type=Path, default=Path.home() / "q50-rasmapper",
                        help="Where the project is copied before mapping.")
    parser.add_argument("--out", type=Path, default=ROOT / "OUTPUT" / "rasmapper",
                        help="Where the generated maps are collected.")
    parser.add_argument("--keep-workspace", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check the environment and the API signature, then stop.")
    args = parser.parse_args(argv)

    if platform.system() != "Windows":
        print("RAS Mapper is part of HEC-RAS, which only runs on Windows.")
        print(f"Detected {platform.system()}. Nothing was run.")
        return 2

    try:
        import ras_commander as rc  # noqa: PLC0415
    except ImportError:
        print("ras-commander is not installed: pip install -r requirements-windows.txt")
        return 2

    print(f"ras-commander {getattr(rc, '__version__', 'unknown')}")
    missing = _check_signature(rc.RasMap.store_all_maps)
    if missing:
        print("This build of ras-commander does not accept: " + ", ".join(missing))
        print("Refusing to call it with parameters it does not declare.")
        print("Full signature:")
        print("  " + str(inspect.signature(rc.RasMap.store_all_maps)))
        return 2
    print("RasMap.store_all_maps accepts every parameter this tool passes.")

    # Checking the signature is not enough. store_all_maps imports RasProcess
    # from inside its own body, and RasProcess imports geopandas -- which
    # ras-commander does not declare as a dependency. A signature check passes
    # happily and the call then dies on ModuleNotFoundError. So resolve the
    # chain here, where it is cheap to report.
    try:
        from ras_commander import RasProcess  # noqa: F401, PLC0415
    except ImportError as exc:
        print(f"The import chain store_all_maps needs is broken: {exc}")
        print("ras-commander pulls this in without declaring it. Install the "
              "Windows requirements: pip install -r requirements-windows.txt")
        return 2
    print("The import chain store_all_maps triggers resolves.")

    # ras-commander wants a version string ("6.6") or a full path to Ras.exe.
    # Handing it the installation *folder* is silently wrong: it joins the base
    # directory to what you gave it and resolves ras_exe_path to the bare name
    # "Ras.exe", which then depends on PATH. compute.py already knows the rule,
    # so the rule lives in one place.
    from q50depth.compute import _resolve_ras_version  # noqa: PLC0415

    try:
        ras_version = _resolve_ras_version(args.ras_dir)
    except Exception as exc:  # ComputeError and anything else
        print(f"--ras-dir does not resolve: {exc}")
        return 2
    print(f"HEC-RAS resolves to {ras_version}")

    if args.dry_run:
        print("--dry-run: stopping before the project is copied.")
        return 0

    # Work on a copy. The delivered data is never mapped in place.
    if args.workspace.exists():
        shutil.rmtree(args.workspace)
    print(f"copying project to {args.workspace} ...")
    shutil.copytree(args.project, args.workspace)

    from q50depth import project as project_module  # noqa: PLC0415

    prj = project_module.find_project_file(args.workspace)
    print(f"project {prj}")

    ras_project = rc.init_ras_project(str(prj.parent), ras_version)

    args.out.mkdir(parents=True, exist_ok=True)
    print(f"asking RAS Mapper for the Q50 maximum depth map, render mode "
          f"'{args.render_mode}' ...")
    summary = rc.RasMap.store_all_maps(
        plan_number=args.plan,
        mode="selected",
        depth=True,
        profile="Max",
        render_mode=args.render_mode,
        output_path=str(args.out),
        ras_object=ras_project,
        ras_version=ras_version,
        raise_on_error=True,
    )
    print("summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    produced = _newest_depth_raster(args.out)
    if produced is None:
        print(f"RAS Mapper reported success but no raster landed in {args.out}.")
        return 1
    print(f"RAS Mapper wrote {produced}")

    from tools.compare_reference import compare  # noqa: PLC0415

    print()
    print("=" * 72)
    print("RAS Mapper's own map  vs  the map this project produced")
    print("=" * 72)
    if args.ours.is_file():
        compare(args.ours, produced)
    else:
        print(f"  (skipped: {args.ours} does not exist yet)")

    if args.reference is not None and args.reference.is_file():
        print()
        print("=" * 72)
        print("RAS Mapper's own map  vs  the client's delivered map")
        print("=" * 72)
        compare(produced, args.reference)

    if not args.keep_workspace:
        shutil.rmtree(args.workspace, ignore_errors=True)
        print(f"\nremoved the working copy at {args.workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
