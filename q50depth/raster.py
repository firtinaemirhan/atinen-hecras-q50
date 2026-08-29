"""GeoTIFF writer.

Besides the pixels, the file carries provenance tags naming the plan, the
short identifier, the simulation window and the source results file.  That is
what makes the deliverable self-verifying: opening the raster is enough to
tell which scenario produced it, without trusting the file name.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS

from .depth import DepthResult
from .errors import Q50Error

NODATA = -9999.0


def crs_from_wkt(wkt: str) -> CRS:
    """Build a CRS from the projection stored in the results file.

    The EPSG code is never assumed.  The model's own WKT (WGS 1984 Transverse
    Mercator, central meridian 30E) is used verbatim, and merely reported
    alongside whatever EPSG code it happens to resolve to.
    """
    try:
        return CRS.from_wkt(wkt)
    except Exception as exc:  # rasterio raises CRSError, a subclass of ValueError
        raise Q50Error(
            f"The projection stored in the results file is not usable: {exc}"
        ) from exc


_PROJCS_NAME = re.compile(r'PROJCS\["([^"]+)"')


def describe(crs: CRS) -> str:
    """Short label for a CRS: its name plus an EPSG code when one exists.

    This model's projection is Transverse Mercator on WGS 84 with central
    meridian 30E and scale factor 1.0. That is *not* UTM zone 36N (which uses
    0.9996), so ``to_epsg()`` legitimately returns nothing and the WKT from the
    results file is the only correct source.
    """
    match = _PROJCS_NAME.search(crs.to_wkt())
    label = match.group(1) if match else "unnamed CRS"
    epsg = crs.to_epsg()
    return f"{label} (EPSG:{epsg})" if epsg else f"{label} (no EPSG equivalent)"


def write(
    path: Path,
    result: DepthResult,
    projection_wkt: str,
    tags: dict[str, str],
) -> Path:
    """Write the depth grid, replacing NaN with the nodata value."""
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    band = result.depth.copy()
    band[~np.isfinite(band)] = NODATA

    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": result.grid.height,
        "width": result.grid.width,
        "crs": crs_from_wkt(projection_wkt),
        "transform": result.grid.transform,
        "nodata": NODATA,
        "compress": "deflate",
        "predictor": 2,
        "zlevel": 6,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "BIGTIFF": "IF_SAFER",
    }
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(band, 1)
        destination.set_band_description(1, "Maximum water depth (m)")
        destination.update_tags(**tags)
    return path
