"""Build the water surface RASMapper draws over a 2D mesh.

HEC-RAS solves for one water surface elevation per computation cell, but that
is not what RASMapper puts on the map.  Which surface it draws is recorded in
the project's own ``.rasmap`` file:

    <RenderMode>sloping</RenderMode>

Two surfaces are therefore implemented here, and the render mode read from the
.rasmap file chooses between them:

``flat``
    One horizontal water surface per cell.  The cell's own maximum water
    surface is painted over the whole cell polygon, so the flood edge follows
    the sub-grid ground inside the cell and looks ragged.  This is what
    RASMapper draws when the render mode is ``horizontal``.

``sloping``
    A continuous surface.  A water surface elevation is first derived at every
    face point (a cell corner) by averaging the cells that meet there, then
    each cell is split into a fan of triangles -- one per edge, all sharing the
    cell centre -- and the surface is interpolated linearly across them.  The
    result is continuous from cell to cell, which is why a RASMapper depth
    grid varies smoothly inside a single cell.

Why the fan and not a Delaunay triangulation: the wet cells form disconnected
clusters, and a Delaunay triangulation of their centres spans the gaps between
them.  Those spanning triangles lay tens of metres of water over the high
ground in between.  The fan uses the mesh's own topology, so a triangle never
reaches beyond the cell it belongs to.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from rasterio.features import rasterize

from .results import Mesh

RENDER_MODES = ("sloping", "flat")

#: What HEC-RAS writes in <RenderMode> and what this module calls it.  The
#: names are not the same: RASMapper's opposite of "sloping" is "horizontal".
_RASMAP_RENDER_MODES = {"sloping": "sloping", "horizontal": "flat"}

_RENDER_MODE = re.compile(r"<RenderMode>\s*([A-Za-z]+)\s*</RenderMode>")


def read_render_mode(rasmap_path: Path) -> str | None:
    """The render mode a RASMapper project draws its result maps with.

    Returns None when the file is missing, unreadable, or names a mode this
    module does not implement -- the caller then falls back to its default
    rather than guessing at a mode whose output was never checked.
    """
    try:
        text = Path(rasmap_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found = {
        _RASMAP_RENDER_MODES[name.lower()]
        for name in _RENDER_MODE.findall(text)
        if name.lower() in _RASMAP_RENDER_MODES
    }
    # More than one mode in one project would mean the map layers disagree;
    # there is no single right answer then, so say nothing.
    return found.pop() if len(found) == 1 else None


def cell_rings(mesh: Mesh, selected: np.ndarray) -> dict[int, np.ndarray]:
    """Face point indexes of each selected cell, in boundary order.

    ``Cells FacePoint Indexes`` lists a cell's corners but not in ring order,
    so the corners are sorted by their angle around the cell centre.  HEC-RAS
    2D cells are convex, which makes that ordering the polygon boundary.
    """
    rings: dict[int, np.ndarray] = {}
    face_points = mesh.face_point_xy
    for cell in np.flatnonzero(selected):
        corners = mesh.cell_face_points[cell]
        corners = corners[corners >= 0]
        if corners.size < 3:
            continue
        points = face_points[corners]
        centre = mesh.cell_center_xy[cell]
        order = np.argsort(
            np.arctan2(points[:, 1] - centre[1], points[:, 0] - centre[0])
        )
        rings[int(cell)] = corners[order]
    return rings


def face_point_cells(mesh: Mesh) -> list[np.ndarray]:
    """For every face point, the real cells that meet at it.

    Inverted from ``Cells FacePoint Indexes``.  HEC-RAS also ships this
    directly as ``FacePoints Cell Info`` / ``FacePoints Cell Index Values``;
    inverting the table we already require gives the identical answer (checked
    against the delivered p05 results: 7399 of 7399 face points agree) and
    keeps the reader dependent on one dataset instead of three.
    """
    neighbours: list[list[int]] = [[] for _ in range(len(mesh.face_point_xy))]
    real = mesh.real_cells
    for cell in np.flatnonzero(real):
        for corner in mesh.cell_face_points[cell]:
            if corner >= 0:
                neighbours[int(corner)].append(int(cell))
    return [np.array(n, dtype=np.int64) for n in neighbours]


def face_point_water_surface(
    mesh: Mesh, selected: np.ndarray, weight_by_area: bool = True
) -> np.ndarray:
    """Water surface elevation at each face point, or NaN where no wet cell.

    Only wet cells contribute.  Letting a dry cell contribute its own bed
    elevation was tried and is worse: on this data set it drags the surface
    down at every flood edge and costs about one point of agreement with the
    reference map.

    The average is weighted by cell surface area when HEC-RAS reports it.  A
    large cell and a small one meeting at a corner do not carry equal weight
    in the surface RASMapper draws; area weighting measurably improves the
    match (72.8% against 71.6% of shared wet area on the Q50 reference).
    """
    values = mesh.max_water_surface.astype("float64")
    areas = mesh.cell_surface_area
    surface = np.full(len(mesh.face_point_xy), np.nan)
    for index, cells in enumerate(face_point_cells(mesh)):
        wet = cells[selected[cells]]
        if wet.size == 0:
            continue
        if weight_by_area and areas is not None:
            weights = areas[wet].astype("float64")
            if weights.sum() > 0:
                surface[index] = np.average(values[wet], weights=weights)
                continue
        surface[index] = values[wet].mean()
    return surface


def _triangles(
    mesh: Mesh, selected: np.ndarray, vertex_surface: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Fan-triangulate every wet cell.

    Returns the triangle corner coordinates (n, 3, 2) and the water surface
    elevation at those corners (n, 3).  A cell is skipped when one of its
    corners has no water surface, which cannot happen for a wet cell -- the
    cell itself is a wet neighbour of each of its own corners -- but is
    checked rather than assumed.
    """
    face_points = mesh.face_point_xy
    centres = mesh.cell_center_xy
    values = mesh.max_water_surface.astype("float64")

    corners: list[np.ndarray] = []
    heights: list[np.ndarray] = []
    for cell, ring in cell_rings(mesh, selected).items():
        if not np.isfinite(vertex_surface[ring]).all():
            continue
        centre = centres[cell]
        height = values[cell]
        for position in range(len(ring)):
            first, second = ring[position], ring[(position + 1) % len(ring)]
            corners.append(
                np.array([face_points[first], face_points[second], centre])
            )
            heights.append(
                np.array(
                    [vertex_surface[first], vertex_surface[second], height]
                )
            )
    if not corners:
        return np.zeros((0, 3, 2)), np.zeros((0, 3))
    return np.array(corners), np.array(heights)


def _interpolate_triangles(
    corners: np.ndarray, heights: np.ndarray, grid
) -> np.ndarray:
    """Linear interpolation across a triangle mesh, onto ``grid``.

    Which triangle covers a pixel is settled by ``rasterio.features.rasterize``
    -- the same routine, and so the same edge rule, that paints the flat
    surface.  The height is then a barycentric blend of that triangle's three
    corners, evaluated for every covered pixel at once.
    """
    out = np.full(grid.shape, np.nan, dtype="float32")
    if len(corners) == 0:
        return out

    shapes = (
        ({"type": "Polygon", "coordinates": [triangle.tolist() + [triangle[0].tolist()]]}, index + 1)
        for index, triangle in enumerate(corners)
    )
    which = rasterize(
        shapes,
        out_shape=grid.shape,
        transform=grid.transform,
        fill=0,
        dtype="int32",
    )
    covered = which > 0
    if not covered.any():
        return out

    rows, cols = np.nonzero(covered)
    # Pixel centres, in the same coordinates as the triangle corners.
    x = grid.transform.c + (cols + 0.5) * grid.transform.a
    y = grid.transform.f + (rows + 0.5) * grid.transform.e
    index = which[covered] - 1

    (x1, y1), (x2, y2), (x3, y3) = (
        (corners[index, 0, 0], corners[index, 0, 1]),
        (corners[index, 1, 0], corners[index, 1, 1]),
        (corners[index, 2, 0], corners[index, 2, 1]),
    )
    denominator = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    # A degenerate triangle covers no pixel centre in practice; guard anyway so
    # a zero denominator becomes NaN rather than a divide-by-zero warning.
    denominator = np.where(np.abs(denominator) < 1e-12, np.nan, denominator)
    first = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / denominator
    second = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / denominator
    third = 1.0 - first - second

    out[rows, cols] = (
        first * heights[index, 0]
        + second * heights[index, 1]
        + third * heights[index, 2]
    ).astype("float32")
    return out


def sloping(mesh: Mesh, selected: np.ndarray, grid) -> np.ndarray:
    """The continuous water surface RASMapper draws in ``sloping`` mode."""
    vertex_surface = face_point_water_surface(mesh, selected)
    corners, heights = _triangles(mesh, selected, vertex_surface)
    return _interpolate_triangles(corners, heights, grid)


def flat(mesh: Mesh, selected: np.ndarray, grid) -> np.ndarray:
    """One horizontal water surface per cell -- RASMapper's ``horizontal``.

    This is what the model itself solves: a single value per computation cell.
    Sub-grid ground inside a cell that stands above that value stays dry.
    """
    shapes = [
        (
            {
                "type": "Polygon",
                "coordinates": [
                    np.vstack(
                        [mesh.face_point_xy[ring], mesh.face_point_xy[ring[:1]]]
                    ).tolist()
                ],
            },
            float(mesh.max_water_surface[cell]),
        )
        for cell, ring in cell_rings(mesh, selected).items()
    ]
    if not shapes:
        return np.full(grid.shape, np.nan, dtype="float32")
    return rasterize(
        shapes,
        out_shape=grid.shape,
        transform=grid.transform,
        fill=np.nan,
        dtype="float32",
    )


def build(mesh: Mesh, selected: np.ndarray, grid, render_mode: str) -> np.ndarray:
    """Dispatch on the render mode read from the .rasmap file."""
    if render_mode == "sloping":
        return sloping(mesh, selected, grid)
    if render_mode == "flat":
        return flat(mesh, selected, grid)
    raise ValueError(
        f"Unknown render mode {render_mode!r}; expected one of {RENDER_MODES}."
    )
