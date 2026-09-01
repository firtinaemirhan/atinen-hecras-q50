"""Builders for miniature HEC-RAS artefacts, used by the depth tests."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import rasterio
from rasterio.transform import from_origin

WKT = (
    'PROJCS["WGS_1984_Transverse_Mercator",GEOGCS["GCS_WGS_1984",'
    'DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["false_easting",500000.0],'
    'PARAMETER["false_northing",0.0],PARAMETER["central_meridian",30.0],'
    'PARAMETER["scale_factor",1.0],PARAMETER["latitude_of_origin",0.0],'
    'UNIT["Meters",1.0]]'
)

SUMMARY = (
    "Results/Unsteady/Output/Output Blocks/Base Output/"
    "Summary Output/2D Flow Areas"
)


def write_terrain_raster(path: Path, elevation: float = 100.0, size: int = 10) -> Path:
    """A flat 1 m terrain covering (0,0)-(size,size)."""
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "width": size,
        "height": size,
        "crs": rasterio.crs.CRS.from_wkt(WKT),
        "transform": from_origin(0, size, 1.0, 1.0),
        "nodata": -9999.0,
    }
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(np.full((size, size), elevation, dtype="float32"), 1)
    return path


def write_terrain_hdf(path: Path, modifications: list[tuple[list, float, str]]) -> Path:
    """``modifications`` is a list of (ring points, elevation value, type)."""
    with h5py.File(path, "w") as handle:
        handle.attrs["File Type"] = np.bytes_(b"HEC Terrain")
        if not modifications:
            return path
        group = handle.create_group("Modifications/buildings")
        info, parts, points = [], [], []
        record = np.dtype(
            [("Name", "S1"), ("Elevation Value", "<f4"), ("Elevation Type", "S11")]
        )
        attributes = np.zeros(len(modifications), dtype=record)
        for index, (ring, value, kind) in enumerate(modifications):
            info.append([len(points), len(ring), len(parts), 1])
            parts.append([0, len(ring)])
            points.extend(ring)
            attributes[index] = (b"", value, kind.encode())
        group.create_dataset("Polygon Info", data=np.array(info, dtype="int32"))
        group.create_dataset("Polygon Parts", data=np.array(parts, dtype="int32"))
        group.create_dataset("Polygon Points", data=np.array(points, dtype="float64"))
        group.create_dataset("Attributes", data=attributes)
    return path


def write_results_hdf(
    path: Path,
    face_points: np.ndarray,
    cell_face_points: np.ndarray,
    cell_centers: np.ndarray,
    cell_min_elevation: np.ndarray,
    max_water_surface: np.ndarray,
    terrain_filename: str,
    cell_surface_area: np.ndarray | None = None,
    mesh_name: str = "mesh",
    plan_title: str = "A_A_B_INPINAR_Q50",
    short_id: str = "Q50",
) -> Path:
    with h5py.File(path, "w") as handle:
        handle.attrs["File Type"] = np.bytes_(b"HEC-RAS Results")
        handle.attrs["File Version"] = np.bytes_(b"HEC-RAS 6.6 September 2024")
        handle.attrs["Projection"] = np.bytes_(WKT.encode())
        handle.attrs["Units System"] = np.bytes_(b"SI Units")

        info = handle.create_group("Plan Data/Plan Information")
        for key, value in {
            "Plan Title": plan_title,
            "Plan ShortID": short_id,
            "Plan Filename": "A_A_B_INPINAR.p05",
            "Geometry Filename": "A_A_B_INPINAR.g03",
            "Geometry Title": "Mevcut_Durum_2D",
            "Flow Filename": "A_A_B_INPINAR.u05",
            "Flow Title": short_id,
            "Time Window": "02May2025 01:00:00 to 02May2025 02:10:00",
        }.items():
            info.attrs[key] = np.bytes_(value.encode())

        unsteady = handle.create_group("Results/Unsteady")
        unsteady.attrs["Short ID"] = np.bytes_(short_id.encode())
        unsteady.attrs["Plan Title"] = np.bytes_(plan_title.encode())

        geometry = handle.create_group("Geometry")
        geometry.attrs["Terrain Filename"] = np.bytes_(terrain_filename.encode())
        geometry.attrs["Terrain Layername"] = np.bytes_(
            terrain_filename.rsplit("/", 1)[-1].split(".")[0].encode()
        )

        areas = handle.create_group("Geometry/2D Flow Areas")
        areas.create_dataset(
            "Attributes",
            data=np.array([(mesh_name.encode(),)], dtype=np.dtype([("Name", "S16")])),
        )
        mesh = areas.create_group(mesh_name)
        mesh.create_dataset("FacePoints Coordinate", data=face_points.astype("float64"))
        mesh.create_dataset("Cells FacePoint Indexes", data=cell_face_points.astype("int32"))
        mesh.create_dataset("Cells Center Coordinate", data=cell_centers.astype("float64"))
        mesh.create_dataset("Cells Minimum Elevation", data=cell_min_elevation.astype("float32"))
        if cell_surface_area is not None:
            mesh.create_dataset(
                "Cells Surface Area", data=cell_surface_area.astype("float32")
            )

        summary = handle.create_group(f"{SUMMARY}/{mesh_name}")
        data = np.vstack(
            [max_water_surface, np.zeros_like(max_water_surface)]
        ).astype("float32")
        dataset = summary.create_dataset("Maximum Water Surface", data=data)
        dataset.attrs["Rows Variables"] = np.array([b"WSEL", b"Time"], dtype="|S16")
        dataset.attrs["Units"] = np.array([b"m", b"days"], dtype="|S16")
    return path
