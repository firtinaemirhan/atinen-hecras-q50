"""Checks that tie the produced raster back to the requested scenario.

The brief asks explicitly how one knows the raster belongs to the right
scenario.  Selecting a plan is not an answer: the run has to be traced from
the scenario label to the plan file, from the plan file to the results file,
and from the results file to the numbers in the grid.
"""

from __future__ import annotations

from dataclasses import dataclass

from .depth import DepthResult
from .errors import VerificationError
from .project import Plan, Project, scenario_pattern
from .results import PlanResults


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

    def line(self) -> str:
        return f"[{'ok' if self.passed else 'FAIL'}] {self.name}: {self.detail}"


def run(
    project: Project,
    plan: Plan,
    scenario: str,
    results: PlanResults,
    depth: DepthResult,
    strict: bool = True,
) -> list[Check]:
    """Return one Check per assertion, raising if a strict run finds a failure."""
    pattern = scenario_pattern(scenario)
    checks: list[Check] = [
        Check(
            "results belong to the selected plan",
            results.plan_filename.lower().endswith(plan.path.name.lower()),
            f"results say plan file {results.plan_filename!r}, selected {plan.path.name!r}",
        ),
        Check(
            "plan title agrees",
            results.plan_title == plan.title,
            f"results {results.plan_title!r} vs plan file {plan.title!r}",
        ),
        Check(
            "short identifier agrees",
            results.plan_short_id == plan.short_id,
            f"results {results.plan_short_id!r} vs plan file {plan.short_id!r}",
        ),
        Check(
            f"results still carry the {scenario} label",
            bool(pattern.search(results.plan_title) or pattern.search(results.plan_short_id)),
            f"title={results.plan_title!r}, short_id={results.plan_short_id!r}",
        ),
        Check(
            "geometry agrees",
            results.geometry_filename.lower().endswith(plan.geometry_file.lower()),
            f"results {results.geometry_filename!r} vs plan {plan.geometry_file!r}",
        ),
        Check(
            "flow file agrees",
            results.flow_filename.lower().endswith(plan.flow_file.lower()),
            f"results {results.flow_filename!r} vs plan {plan.flow_file!r}",
        ),
        Check(
            "the grid holds water",
            depth.wet_pixels > 0 and depth.max_depth > 0,
            f"{depth.wet_pixels} wet pixels, maximum depth {depth.max_depth:.3f} m",
        ),
        Check(
            "depth stays inside the modelled water surface",
            depth.max_water_surface >= depth.terrain_min,
            f"max water surface {depth.max_water_surface:.3f} m, "
            f"terrain minimum {depth.terrain_min:.3f} m",
        ),
    ]

    failed = [c for c in checks if not c.passed]
    if failed and strict:
        raise VerificationError(
            "The output could not be tied to scenario "
            f"{scenario}:\n  " + "\n  ".join(c.line() for c in failed),
            hint="Re-run with --no-verify only if you understand why a check fails.",
        )
    return checks
