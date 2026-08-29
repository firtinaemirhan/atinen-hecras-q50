"""Working copy of the project, and proof the original was left alone.

The brief forbids modifying the delivered project files, but HEC-RAS writes
into the project folder whenever it computes a plan (``.bco``, ``.O0X``,
``.r0X``, and the plan HDF).  So the application always computes on a copy.

To make "the original is untouched" checkable rather than merely asserted, a
manifest of the source tree is taken before the copy and again at the end of
the run, and the two are compared.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import Q50Error

_CHUNK = 1 << 20


@dataclass(frozen=True)
class IntegrityReport:
    mode: str
    file_count: int
    changed: tuple[str, ...]
    added: tuple[str, ...]
    removed: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (self.changed or self.added or self.removed)

    def summary(self) -> str:
        if self.mode == "off":
            return "source integrity check disabled"
        if self.ok:
            return f"source unchanged ({self.file_count} files, {self.mode} check)"
        parts = []
        for label, items in (
            ("modified", self.changed),
            ("added", self.added),
            ("removed", self.removed),
        ):
            if items:
                shown = ", ".join(items[:5])
                more = f" (+{len(items) - 5} more)" if len(items) > 5 else ""
                parts.append(f"{len(items)} {label}: {shown}{more}")
        return "SOURCE CHANGED -> " + "; ".join(parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(root: Path, mode: str = "fast") -> dict[str, str]:
    """Fingerprint every file under ``root``.

    ``fast`` uses size and modification time, which is enough to catch a
    HEC-RAS run writing into the folder.  ``full`` adds a SHA-256 of the file
    contents and costs a few seconds over the ~500 MB data set.
    """
    if mode == "off":
        return {}
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store":
            continue
        stat = path.stat()
        key = str(path.relative_to(root))
        if mode == "full":
            out[key] = f"{stat.st_size}:{_sha256(path)}"
        else:
            out[key] = f"{stat.st_size}:{int(stat.st_mtime)}"
    return out


def compare(before: dict[str, str], after: dict[str, str], mode: str) -> IntegrityReport:
    changed = tuple(sorted(k for k in before.keys() & after.keys() if before[k] != after[k]))
    added = tuple(sorted(after.keys() - before.keys()))
    removed = tuple(sorted(before.keys() - after.keys()))
    return IntegrityReport(mode, len(before), changed, added, removed)


MARKER = ".q50-workspace"


def prepare(source: Path, destination: Path, overwrite: bool) -> Path:
    """Copy the project tree to ``destination`` and return the copy's root.

    A marker file is dropped into the copy.  On a later run the directory may
    be replaced without asking only if that marker is there, so pointing
    ``--workspace`` at an existing directory full of other work cannot quietly
    delete it.
    """
    source = source.resolve()
    destination = destination.expanduser().resolve()

    if destination == source or source in destination.parents:
        raise Q50Error(
            f"Workspace {destination} is inside the source project {source}.",
            hint="Choose a --workspace outside the delivered data folder.",
        )

    if destination.exists():
        if not (destination / MARKER).is_file() and not overwrite:
            raise Q50Error(
                f"{destination} already exists and was not created by this tool.",
                hint="Pass --overwrite-workspace to replace it, or choose another path.",
            )
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    (destination / MARKER).write_text(
        "Working copy created by q50depth. Safe to delete.\n", encoding="utf-8"
    )
    return destination
