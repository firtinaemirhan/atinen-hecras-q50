"""Resolve the terrain the model was built on, including its modifications.

A RASMapper terrain layer is a pair: ``<name>.vrt`` holds the elevation grid,
``<name>.hdf`` holds metadata and any elevation modifications the modeller
drew on top of it.  The modifications are *not* baked into the .vrt; RASMapper
applies them on the fly.

In this data set the geometry is built on ``merge.Clone``, whose .hdf carries
69 building footprints with a +20 m elevation modification.  Reading the .vrt
alone yields ground level inside the buildings, which is 20 m below the bed
HEC-RAS actually computed with.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from .errors import TerrainError

_SUPPORTED_MODIFICATION_TYPES = {"Add"}


@dataclass(frozen=True)
class Modification:
    """One elevation modification polygon."""

    layer: str
    kind: str
    value: float
    rings: tuple[np.ndarray, ...]

    def geojson(self) -> dict:
        return {
            "type": "Polygon",
            "coordinates": [ring.tolist() for ring in self.rings],
        }


@dataclass(frozen=True)
class Terrain:
    """A terrain layer: the elevation raster plus its modifications."""

    hdf_path: Path
    raster_path: Path
    modifications: tuple[Modification, ...]

    @property
    def name(self) -> str:
        return self.hdf_path.stem


def _close_ring(points: np.ndarray) -> np.ndarray:
    if len(points) >= 2 and not np.allclose(points[0], points[-1]):
        return np.vstack([points, points[:1]])
    return points


def _read_modifications(hdf_path: Path) -> tuple[Modification, ...]:
    """Read ``Modifications/<layer>`` polygon groups from a terrain HDF file.

    HEC-RAS stores polygons in four parallel datasets:
      ``Polygon Info``   (n, 4) -> point start, point count, part start, part count
      ``Polygon Parts``  (m, 2) -> ring start (relative to the polygon), ring length
      ``Polygon Points`` (k, 2) -> x, y
      ``Attributes``     (n,)   -> compound record, incl. elevation value and type
    """
    out: list[Modification] = []
    with h5py.File(hdf_path, "r") as handle:
        group = handle.get("Modifications")
        if group is None:
            return ()
        for layer_name, layer in group.items():
            if not isinstance(layer, h5py.Group) or "Polygon Info" not in layer:
                continue
            info = layer["Polygon Info"][...]
            parts = layer["Polygon Parts"][...]
            points = layer["Polygon Points"][...]
            attributes = layer["Attributes"][...]
            for index, (point_start, _count, part_start, part_count) in enumerate(info):
                record = attributes[index]
                kind = record["Elevation Type"]
                kind = kind.decode("latin-1").strip() if isinstance(kind, bytes) else str(kind)
                if kind not in _SUPPORTED_MODIFICATION_TYPES:
                    raise TerrainError(
                        f"Terrain {hdf_path.name} layer {layer_name!r} uses an "
                        f"unsupported elevation modification type {kind!r}.",
                        hint="Only 'Add' is implemented, because that is the only "
                        "type present in this data set and the others were not "
                        "verified against HEC-RAS. Refusing rather than guessing.",
                    )
                rings = tuple(
                    _close_ring(points[point_start + start : point_start + start + length])
                    for start, length in parts[part_start : part_start + part_count]
                )
                out.append(
                    Modification(
                        layer=str(layer_name),
                        kind=kind,
                        value=float(record["Elevation Value"]),
                        rings=rings,
                    )
                )
    return tuple(out)


def resolve(project_folder: Path, terrain_filename: str) -> Terrain:
    """Turn the geometry's ``Terrain Filename`` attribute into a usable terrain.

    The attribute is a Windows-style relative path (``.\\merge.Clone.hdf``),
    so it is normalised before being joined to the project folder.
    """
    if not terrain_filename:
        raise TerrainError(
            "The geometry does not name a terrain.",
            hint="A depth grid is water surface minus terrain; without a terrain "
            "there is nothing to subtract.",
        )

    relative = terrain_filename.replace("\\", "/").lstrip("./")
    hdf_path = (project_folder / relative).resolve()
    if not hdf_path.is_file():
        raise TerrainError(
            f"Terrain file {relative} referenced by the geometry is missing "
            f"from {project_folder}."
        )

    for suffix in (".vrt", ".tif", ".tiff"):
        raster_path = hdf_path.with_suffix(suffix)
        if raster_path.is_file():
            break
    else:
        raise TerrainError(
            f"Terrain {hdf_path.stem} has no elevation raster next to it "
            f"(looked for .vrt, .tif, .tiff in {hdf_path.parent}).",
        )

    return Terrain(
        hdf_path=hdf_path,
        raster_path=raster_path,
        modifications=_read_modifications(hdf_path),
    )
