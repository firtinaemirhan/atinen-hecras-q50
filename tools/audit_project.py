#!/usr/bin/env python3
"""Audit a delivered HEC-RAS project for internal inconsistencies.

The brief says the candidate is expected to work out the file relationships
themselves.  This does that systematically instead of by trial and error: it
reads what the project declares, what each plan needs, and what is actually on
disk, and reports every place those three disagree.

    python tools/audit_project.py --project ~/Desktop/CASE_DATA

Findings are grouped by severity:
    BLOCKER  HEC-RAS cannot load or compute the plan
    WARNING  a reference that does not resolve, but only affects mapping
    NOTE     an observation worth recording
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from q50depth import geometry as geometry_module  # noqa: E402
from q50depth import project as project_module  # noqa: E402

ENCODING = "latin-1"
FILE_KEYS = ("Geom File", "Flow File", "Unsteady File", "Plan File", "DSS File")


def read(path: Path) -> str:
    return path.read_text(encoding=ENCODING) if path.is_file() else ""


def declared(text: str, key: str) -> list[str]:
    return re.findall(rf"^{key}=(\S+)\s*$", text, re.MULTILINE)


def resolve(folder: Path, raw: str) -> Path:
    return folder / raw.replace("\\", "/").lstrip("./")


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, severity: str, topic: str, detail: str) -> None:
        self.rows.append((severity, topic, detail))

    def of(self, severity: str) -> list[tuple[str, str, str]]:
        return [r for r in self.rows if r[0] == severity]

    def render(self) -> str:
        out: list[str] = []
        for severity in ("BLOCKER", "WARNING", "NOTE"):
            rows = self.of(severity)
            if not rows:
                continue
            out.append(f"\n{severity} ({len(rows)})")
            out.append("-" * (len(severity) + 6))
            for _, topic, detail in rows:
                out.append(f"  {topic:<28} {detail}")
        counts = ", ".join(
            f"{len(self.of(s))} {s.lower()}" for s in ("BLOCKER", "WARNING", "NOTE")
        )
        out.append(f"\nSummary: {counts}")
        return "\n".join(out)


def audit(root: Path) -> Report:
    report = Report()
    prj_path = project_module.find_project_file(root)
    folder = prj_path.parent
    stem = prj_path.stem
    prj_text = read(prj_path)

    geometries = declared(prj_text, "Geom File")
    steady = declared(prj_text, "Flow File")
    unsteady = declared(prj_text, "Unsteady File")
    plans = declared(prj_text, "Plan File")

    report.add("NOTE", "project file", f"{prj_path.name}")
    report.add(
        "NOTE",
        "declared by project",
        f"{len(geometries)} geometry, {len(steady)} steady, "
        f"{len(unsteady)} unsteady, {len(plans)} plans",
    )
    current = re.search(r"^Current Plan=(\S+)", prj_text, re.MULTILINE)
    if current:
        report.add("NOTE", "current plan", current.group(1))

    # --- every plan, against the project's own declarations and the disk ---
    for number in plans:
        plan_path = folder / f"{stem}.{number}"
        if not plan_path.is_file():
            report.add("BLOCKER", f"plan {number}", "listed by the project but not on disk")
            continue
        text = read(plan_path)
        geom = (declared(text, "Geom File") or [""])[0]
        flow = (declared(text, "Flow File") or [""])[0]
        title = (re.search(r"^Plan Title=(.*)$", text, re.MULTILINE) or [None, ""])[1]

        if not (folder / f"{stem}.{geom}").is_file():
            report.add("BLOCKER", f"plan {number}", f"geometry {geom} missing from disk")
        elif geom not in geometries:
            report.add(
                "BLOCKER",
                f"plan {number}",
                f"uses geometry {geom}, which the project file does not declare",
            )

        registry = unsteady if flow.startswith("u") else steady
        kind = "unsteady flow" if flow.startswith("u") else "steady flow"
        if not (folder / f"{stem}.{flow}").is_file():
            report.add("BLOCKER", f"plan {number}", f"{kind} {flow} missing from disk")
        elif flow not in registry:
            report.add(
                "BLOCKER",
                f"plan {number}",
                f"uses {kind} {flow}, which the project file does not declare "
                f"(the file exists on disk)",
            )

        for raw in declared(text, "DSS File"):
            if not resolve(folder, raw).exists():
                report.add(
                    "WARNING",
                    f"plan {number} output",
                    f"DSS destination {raw} does not resolve",
                )
        if flow.startswith("u"):
            flow_text = read(folder / f"{stem}.{flow}")
            for raw in declared(flow_text, "DSS File"):
                if not resolve(folder, raw).exists():
                    report.add(
                        "BLOCKER",
                        f"plan {number} inflow",
                        f"boundary condition reads {raw}, which does not resolve",
                    )
            if re.search(r"^Flow Hydrograph= 0\s*$", flow_text, re.MULTILINE):
                report.add(
                    "NOTE",
                    f"plan {number} inflow",
                    f"{flow} stores no hydrograph ordinates; it depends on the DSS file",
                )
        report.add("NOTE", f"plan {number}", f"{title} (geom {geom}, flow {flow})")

    # --- preprocessed geometry tables the unsteady engine reads on start-up ---
    for number in sorted({g for g in geometries}):
        geometry_hdf = folder / f"{stem}.{number}.hdf"
        if not geometry_hdf.is_file():
            report.add("NOTE", f"geometry {number}", "has no preprocessed HDF next to it")
            continue
        absent = geometry_module.missing_tables(geometry_hdf)
        if absent:
            report.add(
                "BLOCKER",
                f"geometry {number}",
                f"{geometry_hdf.name} lacks {', '.join(absent)}; the unsteady engine "
                "reads these and crashes without them",
            )

    # --- files on disk that the project does not declare ---
    for pattern, registry, label in (
        (f"{stem}.u??", unsteady, "unsteady flow"),
        (f"{stem}.g??", geometries, "geometry"),
        (f"{stem}.p??", plans, "plan"),
    ):
        for path in sorted(folder.glob(pattern)):
            suffix = path.suffix.lstrip(".")
            if suffix == "prj":  # the project file itself, not a numbered member
                continue
            if suffix not in registry:
                report.add(
                    "NOTE", "undeclared file", f"{path.name} exists but is not in the project"
                )
    for path in sorted(folder.glob("*.p??")):
        if path.suffix.lower() == ".prj":  # coordinate system files share the pattern
            continue
        if not path.name.startswith(stem):
            report.add(
                "NOTE",
                "stray plan file",
                f"{path.name} looks like a plan but belongs to no project",
            )

    # --- the project's own DSS list ---
    for raw in declared(prj_text, "DSS File"):
        if "/" not in raw and "\\" not in raw:
            report.add("WARNING", "project DSS list", f"malformed entry {raw!r}")
        elif not resolve(folder, raw).exists():
            report.add("WARNING", "project DSS list", f"{raw} does not resolve")

    # --- RASMapper and terrain ---
    rasmap = folder / f"{stem}.rasmap"
    if rasmap.is_file():
        referenced = set(re.findall(r'Filename="([^"]+)"', read(rasmap)))
        missing = sorted(r for r in referenced if not resolve(folder, r).exists())
        report.add(
            "NOTE", "rasmap references", f"{len(referenced)} declared, {len(missing)} missing"
        )
        for raw in missing:
            report.add("WARNING", "rasmap layer", f"{raw} does not resolve")

    for vrt in sorted(folder.glob("*.vrt")):
        for source in re.findall(r"<SourceFilename[^>]*>([^<]+)<", read(vrt)):
            if not (vrt.parent / source).exists():
                report.add("BLOCKER", f"terrain {vrt.name}", f"tile {source} is missing")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.project)
    print(f"Audit of {args.project}")
    print(report.render())
    return 1 if report.of("BLOCKER") else 0


if __name__ == "__main__":
    raise SystemExit(main())
