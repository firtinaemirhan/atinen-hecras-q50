"""Evidence collection must never pass an older file off as this run's output.

The working copy is a copy of the delivered project, and the delivered project
already carries a results file from the client's own successful run.  When an
attempt failed before HEC-RAS wrote anything, an earlier version of the script
read that file and saved the client's 09Jul2026 computation log under a
filename claiming to be tonight's attempt.  Byte for byte the client's log,
labelled as ours.

That is worse than having no evidence, so it is pinned here.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import h5py
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.windows_verify import _collect  # noqa: E402

CLIENT_LOG = "Simulation started at: 09Jul2026 08:48:20 AM\nFinished Unsteady Flow Simulation\n"
OUR_LOG = "Simulation started at: 02Sep2026 01:15:00 AM\nforrtl: severe (157)\n"


def _plan_hdf(path: Path, message: str, modified: float) -> Path:
    with h5py.File(path, "w") as handle:
        handle.create_dataset(
            "Results/Summary/Compute Messages (text)", data=np.bytes_(message.encode())
        )
    import os

    os.utime(path, (modified, modified))
    return path


@pytest.fixture
def workspace(tmp_path: Path):
    """A working copy holding the client's own results, an hour old."""
    folder = tmp_path / "workspace" / "A_A_B_INPINAR_Q50"
    folder.mkdir(parents=True)
    _plan_hdf(folder / "A_A_B_INPINAR.p05.hdf", CLIENT_LOG, time.time() - 3600)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    return tmp_path / "workspace", evidence, folder


def test_a_failed_attempt_does_not_inherit_the_clients_log(workspace):
    root, evidence, _ = workspace
    _collect(root, evidence, "02-rasprocess", started_at=time.time())

    written = (evidence / "02-rasprocess.compute.txt").read_text(encoding="utf-8")
    assert "09Jul2026" not in written, "the client's log leaked into our evidence"
    assert "Finished Unsteady Flow Simulation" not in written
    assert "produced no results file during this attempt" in written


def test_the_stale_file_is_named_so_it_can_be_checked(workspace):
    """Saying 'no evidence' is not enough; say what was there and rejected."""
    root, evidence, _ = workspace
    _collect(root, evidence, "02-rasprocess", started_at=time.time())

    written = (evidence / "02-rasprocess.compute.txt").read_text(encoding="utf-8")
    assert "A_A_B_INPINAR.p05.hdf" in written
    assert "NOT this attempt's output" in written


def test_a_log_the_attempt_did_write_is_kept_with_its_provenance(workspace):
    root, evidence, folder = workspace
    started_at = time.time()
    _plan_hdf(folder / "A_A_B_INPINAR.p05.hdf", OUR_LOG, started_at + 1)

    _collect(root, evidence, "01-ib-rebuild", started_at=started_at)

    written = (evidence / "01-ib-rebuild.compute.txt").read_text(encoding="utf-8")
    assert "forrtl: severe (157)" in written
    assert "09Jul2026" not in written
    # The header has to make the file self-describing.
    assert written.startswith("# source: ")
    assert "# modified: " in written
    assert "# bytes: " in written


def test_a_missing_bco_says_so_rather_than_being_absent(workspace):
    """An absent file reads as 'not looked for'; an explicit note does not."""
    root, evidence, _ = workspace
    _collect(root, evidence, "01-ib-rebuild", started_at=time.time())

    bco = evidence / "01-ib-rebuild.bco.txt"
    assert bco.is_file()
    assert "No .bco run log was written during this attempt" in bco.read_text(
        encoding="utf-8"
    )


def test_a_bco_written_during_the_attempt_is_kept(workspace):
    root, evidence, folder = workspace
    started_at = time.time()
    (folder / "A_A_B_INPINAR.bco05").write_text("run banner\n", encoding="latin-1")

    _collect(root, evidence, "01-ib-rebuild", started_at=started_at)

    written = (evidence / "01-ib-rebuild.bco.txt").read_text(encoding="utf-8")
    assert "run banner" in written
    assert written.startswith("# source: ")
