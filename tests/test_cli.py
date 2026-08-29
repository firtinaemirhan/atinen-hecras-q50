"""Command line behaviour, including the failure paths."""

from __future__ import annotations

from pathlib import Path

from q50depth.cli import main


def test_ras_dir_is_required_for_a_real_run(case_project: Path, tmp_path: Path, capsys):
    code = main(["--project", str(case_project), "--output", str(tmp_path / "out.tif")])
    assert code == 2  # UsageError
    assert "--ras-dir is required" in capsys.readouterr().out


def test_missing_project_exits_cleanly(tmp_path: Path, capsys):
    empty = tmp_path / "nothing"
    empty.mkdir()
    code = main(["--project", str(empty), "--use-existing-results"])
    assert code == 3  # ProjectError
    assert "No HEC-RAS project file" in capsys.readouterr().out


def test_unknown_scenario_exits_cleanly(case_project: Path, tmp_path: Path, capsys):
    code = main(
        [
            "--project", str(case_project),
            "--use-existing-results",
            "--scenario", "Q25",
            "--output", str(tmp_path / "out.tif"),
        ]
    )
    assert code == 4  # ScenarioError
    out = capsys.readouterr().out
    assert "No plan" in out and "Q25" in out


def test_missing_results_exits_cleanly(case_project: Path, tmp_path: Path, capsys):
    """The synthetic project has plan files but no computed results."""
    code = main(
        [
            "--project", str(case_project),
            "--use-existing-results",
            "--output", str(tmp_path / "out.tif"),
        ]
    )
    assert code == 6  # ResultsError
    assert "No results file" in capsys.readouterr().out


def test_nothing_crashes_without_a_traceback(case_project: Path, tmp_path: Path, capsys):
    main(["--project", str(case_project), "--use-existing-results",
          "--output", str(tmp_path / "out.tif")])
    assert "Traceback" not in capsys.readouterr().out
