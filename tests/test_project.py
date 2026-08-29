from __future__ import annotations

import re
from pathlib import Path

import pytest

from q50depth import project
from q50depth.errors import ProjectError, ScenarioError


def test_finds_the_hec_ras_prj_and_ignores_coordinate_files(case_project: Path):
    found = project.find_project_file(case_project.parent)
    assert found.name == "A_A_B_INPINAR.prj"


def test_project_file_is_found_from_a_grandparent_folder(case_project: Path):
    assert project.find_project_file(case_project.parent).parent == case_project


def test_missing_project_is_reported(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ProjectError, match="No HEC-RAS project file"):
        project.find_project_file(tmp_path / "empty")


def test_plan_list_comes_from_the_project_file_not_the_folder(case_project: Path):
    loaded = project.load_project(case_project / "A_A_B_INPINAR.prj")
    numbers = [p.number for p in loaded.plans]
    assert numbers == ["p03", "p02", "p01", "p04", "p05", "p06", "p07"]
    assert (case_project / "Backup.p01").exists()
    assert all(p.path.name != "Backup.p01" for p in loaded.plans)


def test_short_identifier_padding_is_stripped(case_project: Path):
    loaded = project.load_project(case_project / "A_A_B_INPINAR.prj")
    assert [p.short_id for p in loaded.plans if p.number == "p05"] == ["Q50"]


def test_q50_selects_exactly_p05(case_project: Path):
    loaded = project.load_project(case_project / "A_A_B_INPINAR.prj")
    plan, evidence = project.select_plan(loaded, "Q50")
    assert plan.number == "p05"
    assert evidence["p05"] == ["Plan Title", "Short Identifier"]
    assert set(evidence) == {"p05"}


@pytest.mark.parametrize(
    "scenario,expected", [("Q50", "p05"), ("Q100", "p06"), ("Q1000", "p07")]
)
def test_other_return_periods_resolve_to_their_own_plan(case_project: Path, scenario, expected):
    loaded = project.load_project(case_project / "A_A_B_INPINAR.prj")
    plan, _ = project.select_plan(loaded, scenario)
    assert plan.number == expected


def test_q500_is_genuinely_ambiguous_in_this_project(case_project: Path):
    """Not a defect: p03's short id is INPINAR_Q500_UNSTEADY and p04 is Q500.

    Two plans really do carry the Q500 label, so refusing is the correct
    answer. It is asserted here so the behaviour is not "fixed" later by
    silently picking the first match.
    """
    loaded = project.load_project(case_project / "A_A_B_INPINAR.prj")
    with pytest.raises(ScenarioError, match="matches 2 plans"):
        project.select_plan(loaded, "Q500")


def test_unknown_scenario_fails_loudly(case_project: Path):
    loaded = project.load_project(case_project / "A_A_B_INPINAR.prj")
    with pytest.raises(ScenarioError, match="No plan .* matches scenario Q25"):
        project.select_plan(loaded, "Q25")


def test_ambiguous_scenario_fails_loudly(case_project: Path, tmp_path: Path):
    from tests.conftest import write_plan

    write_plan(case_project, "A_A_B_INPINAR", "p08", "COPY_OF_Q50", "Q50", "g03", "u05")
    prj = case_project / "A_A_B_INPINAR.prj"
    prj.write_text(prj.read_text(encoding="latin-1") + "Plan File=p08\n", encoding="latin-1")
    loaded = project.load_project(prj)
    with pytest.raises(ScenarioError, match="matches 2 plans"):
        project.select_plan(loaded, "Q50")


class TestScenarioPattern:
    """The substring trap, isolated."""

    @pytest.mark.parametrize("text", ["Q50", "A_A_B_INPINAR_Q50", "Q050", "x Q50 y", "q50"])
    def test_matches(self, text):
        assert project.scenario_pattern("Q50").search(text)

    @pytest.mark.parametrize(
        "text", ["Q500", "INPINAR_Q500_UNSTEADY", "Q5000", "Q100", "Q1000", "Q5"]
    )
    def test_does_not_match(self, text):
        assert not project.scenario_pattern("Q50").search(text)

    def test_naive_substring_search_would_be_wrong(self):
        """Documents why the lookarounds exist."""
        assert "Q50" in "INPINAR_Q500_UNSTEADY"
        assert not project.scenario_pattern("Q50").search("INPINAR_Q500_UNSTEADY")

    def test_rejects_nonsense(self):
        with pytest.raises(ScenarioError):
            project.scenario_pattern("fifty")
