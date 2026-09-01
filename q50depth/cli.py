"""Command line entry point and run orchestration."""

from __future__ import annotations

import argparse
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import (
    __version__,
    compute,
    depth,
    geometry,
    hydrograph,
    logging_setup,
    project,
    raster,
    references,
    results,
    surface,
    terrain,
    verify,
    workspace,
)
from .errors import ComputeError, Q50Error, UsageError

DEFAULT_SCENARIO = "Q50"
DEFAULT_OUTPUT = Path("OUTPUT/q50_depth.tif")
DEFAULT_WORKSPACE = Path("workspace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="q50depth",
        description=(
            "Find a return-period scenario in a HEC-RAS project, compute it, and "
            "write the maximum water depth as a GeoTIFF."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  # full run on Windows, HEC-RAS installed\n"
            '  python main.py --project "D:/CASE_DATA" '
            '--ras-dir "C:/Program Files (x86)/HEC/HEC-RAS/6.6"\n\n'
            "  # rebuild the raster from results that already exist (no HEC-RAS needed)\n"
            "  python main.py --project /path/to/CASE_DATA --use-existing-results\n"
        ),
    )
    parser.add_argument(
        "--project",
        required=True,
        type=Path,
        metavar="PATH",
        help="HEC-RAS project folder (or any folder containing it).",
    )
    parser.add_argument(
        "--ras-dir",
        type=Path,
        metavar="PATH",
        help="HEC-RAS installation folder, or the full path to Ras.exe. "
        "Required unless --use-existing-results is given.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        metavar="PATH",
        help=f"Output GeoTIFF (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_SCENARIO,
        metavar="Qnnn",
        help=f"Return-period label to look for (default: {DEFAULT_SCENARIO}).",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        metavar="PATH",
        help=f"Where the project is copied before computing (default: {DEFAULT_WORKSPACE}).",
    )
    parser.add_argument(
        "--overwrite-workspace",
        action="store_true",
        help="Replace the workspace even if this tool did not create it.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Do not report the workspace as removable at the end (it is never "
        "deleted automatically; this only affects the closing message).",
    )
    parser.add_argument(
        "--use-existing-results",
        action="store_true",
        help="Skip the HEC-RAS run and read the results already in the project. "
        "For development and for re-deriving the raster; the delivered run "
        "computes the plan.",
    )
    parser.add_argument(
        "--trim-project",
        choices=("auto", "always", "never"),
        default="auto",
        help="Reduce the working copy's project file to the selected plan and "
        "its inputs. 'auto' (default) does this only when another plan in the "
        "project is broken, because HEC-RAS aborts the whole project load in "
        "that case. Never touches the delivered project.",
    )
    parser.add_argument(
        "--geometry",
        choices=("auto", "rasprocess", "harvest", "none"),
        default="auto",
        help="How to supply the preprocessed geometry tables the delivery is "
        "missing. 'auto' (default) asks HEC-RAS's own RasProcess.exe to write "
        "them and, if that is unavailable, takes them from the complete "
        "geometry inside the delivered results file. 'rasprocess' and "
        "'harvest' force one of the two; 'none' leaves the geometry alone.",
    )
    parser.add_argument(
        "--inflow",
        choices=("dss", "inline"),
        default="dss",
        help="Where the boundary condition hydrograph comes from. 'dss' "
        "(default) leaves the model reading its DSS file. 'inline' reads the "
        "series from the DSS text export that ships with the project and "
        "writes it into the working copy's flow file, so the run no longer "
        "depends on HEC-RAS opening the DSS.",
    )
    parser.add_argument(
        "--rasmapper",
        choices=("off", "on"),
        default="off",
        help="Whether HEC-RAS should also run RASMapper's stored-map generation "
        "after computing. Off by default: this application produces the raster "
        "itself, and the delivered RASMapper configuration references scenario "
        "layers that are not in the delivery. Only the working copy is changed.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Build the working copy (copy, repair paths, reduce the project) "
        "and stop, without reading results or writing a raster. Useful for "
        "opening the prepared project in the HEC-RAS GUI.",
    )
    parser.add_argument(
        "--runner",
        choices=compute.RUNNERS,
        default="cmdr",
        help="How to drive HEC-RAS: 'cmdr' = command line runner (default), "
        "'controller' = HECRASController COM automation.",
    )
    parser.add_argument(
        "--cores",
        type=int,
        metavar="N",
        help="Cores HEC-RAS may use (default: let HEC-RAS decide).",
    )
    parser.add_argument(
        "--resolution",
        type=float,
        metavar="METRES",
        help="Output pixel size. Default: the terrain's own resolution, which "
        "needs no resampling.",
    )
    parser.add_argument(
        "--min-depth",
        type=float,
        default=0.0,
        metavar="METRES",
        help="Depths at or below this become nodata (default: 0.0, i.e. keep any water). "
        "The delivered reference maps were cut at 0.01 m.",
    )
    parser.add_argument(
        "--grid-like",
        type=Path,
        metavar="RASTER",
        help="Write the output on this raster's exact pixel grid instead of "
        "the terrain's. Use it to put the result on the same pixels as a "
        "reference map so the two can be compared cell for cell; the terrain "
        "is resampled onto that grid with nearest neighbour.",
    )
    parser.add_argument(
        "--render-mode",
        choices=("auto", "sloping", "flat"),
        default="auto",
        help="Which water surface to draw. 'auto' (default) reads <RenderMode> "
        "out of the project's own .rasmap file, so the map is built the way "
        "the modeller configured RASMapper; it falls back to 'sloping' when "
        "the file says nothing. 'sloping' interpolates a continuous surface "
        "between cells, 'flat' paints one level per cell.",
    )
    parser.add_argument(
        "--wet-tolerance",
        type=float,
        default=depth.DEFAULT_WET_TOLERANCE,
        metavar="METRES",
        help="A cell counts as wet only this far above its own bed (default: "
        f"{depth.DEFAULT_WET_TOLERANCE}). HEC-RAS reports a never-wet cell at its own "
        "bed elevation, but only to within float32 rounding; without a "
        "tolerance those cells join the water surface.",
    )
    parser.add_argument(
        "--integrity",
        choices=("fast", "full", "off"),
        default="fast",
        help="How to prove the source data was not modified: 'fast' = size and "
        "timestamp (default), 'full' = SHA-256 of every file, 'off' = skip.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Report the scenario checks but do not fail on them.",
    )
    parser.add_argument("--log", type=Path, metavar="PATH", help="Run log file "
                        "(default: <output folder>/run.log).")
    parser.add_argument("--verbose", action="store_true", help="Debug output on the console.")
    parser.add_argument("--version", action="version", version=f"q50depth {__version__}")
    return parser


def _describe_plans(log, selected, evidence, all_plans) -> None:
    log.info("")
    log.info("Plans listed by the project file:")
    for plan in all_plans:
        mark = ">>" if plan.number == selected.number else "  "
        why = f"   <- matched on {', '.join(evidence[plan.number])}" if plan.number in evidence else ""
        log.info(
            f"  {mark} {plan.number}  {plan.title:<28}  short id: {plan.short_id:<24}"
            f"geom {plan.geometry_file}  flow {plan.flow_file}{why}"
        )
    log.info("")


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    output = args.output.expanduser()
    log_path = (args.log or output.parent / "run.log").expanduser()
    log = logging_setup.configure(log_path, args.verbose)
    started = time.monotonic()

    log.info(f"q50depth {__version__}  on {platform.system()} {platform.release()}, "
             f"python {platform.python_version()}")
    log.info(f"started {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}")
    log.debug(f"arguments: {vars(args)}")

    if args.use_existing_results and args.ras_dir is not None:
        log.warning("note: --ras-dir is ignored because --use-existing-results was given")
    if not (args.use_existing_results or args.prepare_only) and args.ras_dir is None:
        raise UsageError(
            "--ras-dir is required to run HEC-RAS.",
            hint="Give the HEC-RAS installation folder, or pass "
            "--use-existing-results to rebuild the raster from results that "
            "are already in the project.",
        )

    # ---- 1. find the project and resolve the scenario to exactly one plan ----
    source_prj = project.find_project_file(args.project)
    source_folder = source_prj.parent
    log.info(f"[1/6] project     {source_prj}")
    source_project = project.load_project(source_prj)
    selected, evidence = project.select_plan(source_project, args.scenario)
    _describe_plans(log, selected, evidence, source_project.plans)
    log.info(
        f"[2/6] scenario    {args.scenario} -> {selected.number} "
        f"(pattern {project.scenario_pattern(args.scenario).pattern})"
    )
    if source_project.current_plan:
        agrees = "agrees" if source_project.current_plan == selected.number else "DIFFERS"
        log.info(
            f"      the project's own 'Current Plan={source_project.current_plan}' "
            f"{agrees} with the selection (not used to decide)"
        )

    # ---- 2. working copy, so the delivered data stays untouched ----
    before = workspace.manifest(source_folder, args.integrity)
    if args.use_existing_results:
        working_folder, working_prj = source_folder, source_prj
        log.info("[3/6] workspace   skipped (--use-existing-results reads the project read-only)")
    else:
        target = args.workspace / f"{source_prj.stem}_{args.scenario}"
        log.info(f"[3/6] workspace   copying project to {target}")
        working_folder = workspace.prepare(source_folder, target, args.overwrite_workspace)
        working_prj = working_folder / source_prj.name

    # ---- 3. make the working copy something HEC-RAS can actually load ----
    working_plan = working_folder / selected.path.name
    plan_references = references.collect(working_folder, working_plan, selected.flow_file)
    unresolved = [r for r in plan_references if not r.exists]
    for reference in unresolved:
        log.warning(
            f"      note: {selected.number} reads {reference.raw} ({reference.kind}), "
            "which does not resolve in the project as delivered"
        )
    defects = project.plan_defects(source_project)
    for defect in defects:
        log.warning(f"      note: {defect.line()}")

    if args.use_existing_results:
        log.info("[4/6] hec-ras     not run; using the results already in the project")
        if unresolved or defects:
            log.info("      the notes above only matter for a real HEC-RAS run")
    else:
        if unresolved:
            log.info(f"[4/6] prepare     repairing {len(unresolved)} unresolved path(s)")
            for repair in references.repair(working_folder, plan_references):
                log.info(f"      {repair.line()}")

        # HEC-RAS loads every plan a project declares, so one plan it cannot
        # assemble aborts the load for all of them -- including ours.
        others = [d for d in defects if d.plan != selected.number]
        trim = args.trim_project == "always" or (
            args.trim_project == "auto" and bool(others)
        )
        if trim:
            if others:
                log.info(
                    f"      {len(others)} unrelated plan(s) in this project cannot be "
                    "loaded by HEC-RAS; reducing the working copy to the selected plan"
                )
            dropped = project.write_reduced(working_prj, selected)
            log.info(
                f"      {working_prj.name} now declares only {selected.number}, "
                f"{selected.geometry_file}, {selected.flow_file} "
                f"({len(dropped)} declarations removed)"
            )
            for line in dropped:
                log.debug(f"        removed: {line}")

        if args.geometry != "none":
            geometry_hdf = working_folder / f"{working_prj.stem}.{selected.geometry_file}.hdf"
            absent = geometry.missing_tables(geometry_hdf)
            if absent:
                log.info(
                    f"[4/6] geometry    {geometry_hdf.name} is missing "
                    f"{len(absent)} preprocessed group(s) the unsteady engine reads: "
                    + ", ".join(a.split("/", 1)[1] for a in absent)
                )
                aligned = geometry.align_terrain_timestamp(geometry_hdf, working_folder)
                if aligned:
                    log.info(
                        "      set the terrain timestamp to the one the geometry "
                        f"records ({aligned}), so HEC-RAS does not call it updated"
                    )

                authored_by_hecras = False
                if args.geometry in ("auto", "rasprocess") and args.ras_dir is not None:
                    rasmap = working_folder / f"{working_prj.stem}.rasmap"
                    ran, detail = geometry.complete_with_hecras(
                        geometry_hdf, rasmap if rasmap.is_file() else None, args.ras_dir
                    )
                    log.info(f"      {detail}")
                    if ran:
                        absent = geometry.missing_tables(geometry_hdf)
                        authored_by_hecras = not absent
                        log.info(
                            "      HEC-RAS wrote the tables itself"
                            if authored_by_hecras
                            else "      still missing: "
                            + ", ".join(a.split("/", 1)[1] for a in absent)
                        )

                if absent and args.geometry in ("auto", "harvest"):
                    repair = geometry.rebuild_from_results(
                        geometry_hdf, results.results_path_for(selected.path)
                    )
                    log.info(f"      {repair.line()}")
                    absent = geometry.missing_tables(geometry_hdf)

                if absent:
                    raise ComputeError(
                        f"{geometry_hdf.name} still lacks {', '.join(absent)}.",
                        hint="The unsteady engine reads these on start-up and "
                        "crashes without them.",
                    )

                if not authored_by_hecras:
                    # Tables taken from the results file carry no source-data
                    # hash, so HEC-RAS would rebuild -- and lose -- them.
                    previous = project.set_plan_flag(working_plan, "Run HTab", " 0 ")
                    if previous is not None and previous.strip() != "0":
                        log.info(
                            "      told HEC-RAS not to re-run the geometry "
                            f"preprocessor (Run HTab {previous.strip()} -> 0)"
                        )

        if args.inflow == "inline":
            flow_path = working_folder / f"{working_prj.stem}.{selected.flow_file}"
            pathname = hydrograph.dss_pathname(flow_path)
            if pathname is None:
                log.info(f"      {flow_path.name} reads no DSS series; nothing to embed")
            else:
                dss_reference = next(
                    (r for r in plan_references if r.kind == "inflow"), None
                )
                export = (
                    hydrograph.find_text_export(dss_reference.path, working_folder)
                    if dss_reference
                    else None
                )
                if export is None:
                    raise UsageError(
                        "No DSS text export was found in the project, so the "
                        "inflow cannot be embedded.",
                        hint="Leave --inflow at dss.",
                    )
                series = hydrograph.read_series(export, pathname)
                hydrograph.embed(flow_path, series)
                log.info(
                    f"      embedded the inflow into {flow_path.name} from "
                    f"{export.name}: {series.summary()}"
                )
                log.info(f"      series {series.pathname}")

        if args.rasmapper == "off":
            previous = project.set_plan_flag(working_plan, "Run RASMapper", " 0 ")
            if previous is not None and previous != "0":
                log.info(
                    "      switched RASMapper stored-map generation off in the "
                    f"working copy (was {previous}); the raster is built here, not there"
                )

        if not args.prepare_only and compute.clear_stale_results(
            results.results_path_for(working_plan)
        ):
            log.info("      removed the previous results file from the working copy")

    if args.prepare_only:
        log.info("")
        log.info(f"--prepare-only: the working copy is ready at {working_folder}")
        log.info(f"Open {working_prj.name} in HEC-RAS to inspect the plan by hand.")
        return 0

    if not args.use_existing_results:
        log.info(f"[4/6] hec-ras     computing {selected.number} via {args.runner}")
        outcome = compute.run_plan(
            project_folder=working_folder,
            prj_path=working_prj,
            plan_number=selected.number,
            ras_dir=args.ras_dir,
            runner=args.runner,
            cores=args.cores,
        )
        log.info(f"      {outcome.detail}, {outcome.seconds:.1f} s")
        try:
            compute.verify_results(
                results.results_path_for(working_plan), working_prj, selected.number
            )
        except ComputeError as failure:
            # Say whether the repaired geometry survived the run. Without this
            # one cannot tell "HEC-RAS rebuilt and lost the tables" from
            # "the tables were there and something else broke".
            after = geometry.missing_tables(
                working_folder / f"{working_prj.stem}.{selected.geometry_file}.hdf"
            )
            state = (
                "the geometry still has its preprocessed tables, so the crash is "
                "not about them"
                if not after
                else "HEC-RAS rebuilt the geometry during the run and dropped: "
                + ", ".join(a.split("/", 1)[1] for a in after)
            )
            raise ComputeError(
                failure.message, f"{failure.hint or ''}\n  After the run: {state}"
            ) from failure

    # ---- 5. read results, terrain, and build the depth grid ----
    hdf_path = results.results_path_for(working_plan)
    plan_results = results.load(hdf_path)
    log.info(f"[5/6] results     {hdf_path.name}")
    log.info(f"      plan '{plan_results.plan_title}', short id '{plan_results.plan_short_id}', "
             f"{plan_results.program_version}")
    log.info(f"      window {plan_results.simulation_window}")
    log.info(f"      2D areas: " + ", ".join(
        f"{m.name} ({m.cell_count} cells)" for m in plan_results.meshes))

    model_terrain = terrain.resolve(working_folder, plan_results.terrain_filename)
    log.info(f"      terrain {model_terrain.raster_path.name}"
             + (f" + {len(model_terrain.modifications)} elevation modifications"
                if model_terrain.modifications else " (no modifications)"))

    render_mode = args.render_mode
    if render_mode == "auto":
        rasmap_path = working_prj.with_suffix(".rasmap")
        from_project = surface.read_render_mode(rasmap_path)
        render_mode = from_project or "sloping"
        log.info(
            f"      render mode '{render_mode}' "
            + (f"read from {rasmap_path.name}" if from_project
               else f"({rasmap_path.name} names no mode this build knows; using the default)")
        )
    else:
        log.info(f"      render mode '{render_mode}' (given on the command line)")

    output_grid = None
    if args.grid_like is not None:
        if not args.grid_like.is_file():
            raise UsageError(f"--grid-like: no such raster: {args.grid_like}")
        output_grid = depth.grid_of(args.grid_like)
        log.info(f"      grid taken from {args.grid_like.name} "
                 f"({output_grid.width} x {output_grid.height} @ "
                 f"{output_grid.resolution:g} m)")

    depth_result = depth.build(
        plan_results,
        model_terrain,
        resolution=args.resolution,
        min_depth=args.min_depth,
        wet_tolerance=args.wet_tolerance,
        render_mode=render_mode,
        grid=output_grid,
    )
    log.info(f"      grid {depth_result.grid.width} x {depth_result.grid.height} @ {depth_result.grid.resolution:g} m")
    log.info(f"      wet cells {depth_result.wet_cells}/{depth_result.total_cells}, wet pixels {depth_result.wet_pixels}")
    log.info(f"      depth max {depth_result.max_depth:.3f} m, mean {depth_result.mean_depth:.3f} m")

    # ---- 5. verification ----
    checks = verify.run(
        source_project, selected, args.scenario, plan_results, depth_result, strict=not args.no_verify
    )
    log.info("")
    log.info("Scenario verification:")
    for check in checks:
        log.info(f"  {check.line()}")
    log.info("")

    # ---- 6. write ----
    crs = raster.crs_from_wkt(plan_results.projection_wkt)
    tags = {
        "TIFFTAG_SOFTWARE": f"q50depth {__version__}",
        "SCENARIO": args.scenario,
        "PLAN_NUMBER": selected.number,
        "PLAN_TITLE": plan_results.plan_title,
        "PLAN_SHORT_ID": plan_results.plan_short_id,
        "GEOMETRY": plan_results.geometry_filename,
        "FLOW_FILE": plan_results.flow_filename,
        "SIMULATION_WINDOW": plan_results.simulation_window,
        "HEC_RAS_VERSION": plan_results.program_version,
        "SOURCE_RESULTS": hdf_path.name,
        "TERRAIN": model_terrain.raster_path.name,
        "TERRAIN_MODIFICATIONS": str(len(model_terrain.modifications)),
        "QUANTITY": "maximum water depth",
        "SURFACE_METHOD": "horizontal (cell-wise)",
        "UNITS": "m",
        "COMPUTED_AT": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "HEC_RAS_EXECUTED": str(not args.use_existing_results),
    }
    written = raster.write(output, depth_result, plan_results.projection_wkt, tags)
    size_mb = written.stat().st_size / 1e6
    log.info(f"[6/6] output      {written}  ({size_mb:.1f} MB, {raster.describe(crs)})")

    # ---- source integrity ----
    after = workspace.manifest(source_folder, args.integrity)
    report = workspace.compare(before, after, args.integrity)
    log.info(f"      integrity   {report.summary()}")
    if not report.ok:
        log.warning("      the delivered data was modified -- this must not happen")

    log.info("")
    log.info(f"done in {time.monotonic() - started:.1f} s. Log: {log_path}")
    if not args.use_existing_results and not args.keep_workspace:
        log.info(f"The working copy in {working_folder} can be deleted.")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except Q50Error as error:
        log = logging_setup.get()
        emit = log.error if log.handlers else (lambda message: print(message, file=sys.stderr))
        emit("")
        emit(f"ERROR: {error.message}")
        if error.hint:
            emit(f"       {error.hint}")
        return error.exit_code
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception:  # unexpected: this is a bug, show everything
        log = logging_setup.get()
        if log.handlers:
            log.exception("Unhandled error -- this is a bug in q50depth.")
        else:
            raise
        return 70
