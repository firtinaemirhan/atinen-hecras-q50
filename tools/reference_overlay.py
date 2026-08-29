#!/usr/bin/env python3
"""Draw the project's 1D geometry over the depth raster, at the raster's own scale.

The reference image shown in the kick-off meeting has a smooth, unbroken ribbon
running along the channel, while the depth map produced here shows scattered
flood patches.  This tool answers whether that ribbon is water by putting the
1D geometry on top of the depth grid in real coordinates:

    python tools/reference_overlay.py \\
        --geometry <CASE_DATA>/.../A_A_B_INPINAR.g01 \\
        -o docs/referans_karsilastirma.png

The centreline and the cross section cut lines come out of the geometry file
verbatim; nothing is drawn by eye.  The numbers printed are the ones quoted in
the report.  Pass --reference to stack a screenshot above the map for a
side-by-side; the screenshot is only pasted, never registered or warped.

Needs matplotlib (requirements-dev.txt); the pipeline itself does not.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.plot import plotting_extent  # noqa: E402

FIELD = 16  # HEC-RAS writes coordinate blocks as fixed 16-character fields.


def _coordinates(lines: list[str], count: int) -> np.ndarray:
    """Read ``count`` (x, y) pairs from fixed-width HEC-RAS coordinate lines.

    The fields are not separated by whitespace when a number is wide enough to
    fill its column, so the block cannot be split on spaces.
    """
    numbers: list[float] = []
    for line in lines:
        for start in range(0, len(line.rstrip("\n")), FIELD):
            chunk = line[start : start + FIELD].strip()
            if chunk:
                numbers.append(float(chunk))
        if len(numbers) >= count * 2:
            break
    return np.asarray(numbers[: count * 2], dtype=float).reshape(-1, 2)


def _blocks(geometry_text: str, key: str) -> list[np.ndarray]:
    """Every ``key=<count>`` block in the geometry file, as coordinate arrays."""
    lines = geometry_text.splitlines()
    found: list[np.ndarray] = []
    for index, line in enumerate(lines):
        if not line.startswith(f"{key}="):
            continue
        count = int(line.split("=", 1)[1].strip())
        found.append(_coordinates(lines[index + 1 :], count))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raster", type=Path, nargs="?", default=Path("OUTPUT/q50_depth.tif"))
    parser.add_argument("--geometry", type=Path, required=True, help="1D geometry file (.g01).")
    parser.add_argument("--reference", type=Path, help="Screenshot to stack above the map.")
    parser.add_argument("-o", "--output", type=Path, default=Path("docs/referans_karsilastirma.png"))
    args = parser.parse_args()

    text = args.geometry.read_text(errors="replace")
    centrelines = _blocks(text, "Reach XY")
    cut_lines = _blocks(text, "XS GIS Cut Line")
    declared = text.count("Type RM Length L Ch R")

    with rasterio.open(args.raster) as source:
        depth = source.read(1, masked=True).astype("float32").filled(np.nan)
        extent = plotting_extent(source)
        bounds = source.bounds
        tags = source.tags()

    print(f"{args.geometry.name}")
    print(f"  centrelines      {len(centrelines)}"
          f" ({', '.join(str(len(c)) + ' points' for c in centrelines)})")
    print(f"  cross sections   {declared} declared, {len(cut_lines)} with a GIS cut line")
    print(f"  cut line points  {[len(c) for c in cut_lines]}")
    for name, geometry in (("centreline", centrelines), ("cut lines", cut_lines)):
        if not geometry:
            continue
        stacked = np.vstack(geometry)
        print(f"  {name:<16} x {stacked[:, 0].min():.1f}..{stacked[:, 0].max():.1f}"
              f"   y {stacked[:, 1].min():.1f}..{stacked[:, 1].max():.1f}")
    print(f"{args.raster.name}")
    print(f"  raster extent    x {bounds.left:.1f}..{bounds.right:.1f}"
          f"   y {bounds.bottom:.1f}..{bounds.top:.1f}")

    inside = 0
    for line in cut_lines:
        centre = line.mean(axis=0)
        if bounds.left <= centre[0] <= bounds.right and bounds.bottom <= centre[1] <= bounds.top:
            inside += 1
    print(f"  cut lines inside the raster extent: {inside}/{len(cut_lines)}")

    rows = 2 if args.reference else 1
    figure, axes = plt.subplots(
        rows, 1, figsize=(14, 5.2 * rows), gridspec_kw={"height_ratios": [1] * rows}
    )
    axes = np.atleast_1d(axes)

    if args.reference:
        axes[0].imshow(mpimg.imread(args.reference))
        axes[0].set_title("Referans çıktı — toplantıda gösterilen görüntü", loc="left", fontsize=11)
        axes[0].axis("off")

    map_axes = axes[-1]
    map_axes.imshow(np.isfinite(depth), extent=extent, cmap="Greys", vmin=0, vmax=1.6)
    for line in centrelines:
        map_axes.plot(line[:, 0], line[:, 1], color="#1f4fd8", linewidth=1.8,
                      label="1D nehir ekseni (talveg)")
    for line in cut_lines:
        map_axes.plot(line[:, 0], line[:, 1], color="#2dd4bf", linewidth=1.1,
                      label=f"1D kesit çizgileri ({len(cut_lines)} adet)")
    handles, labels = map_axes.get_legend_handles_labels()
    unique = dict(zip(labels, handles))
    map_axes.legend(unique.values(), unique.keys(), loc="lower left", fontsize=9, framealpha=0.9)
    map_axes.set_title(
        f"Üretilen {tags.get('SCENARIO', '?')} maksimum derinlik haritası — aynı alan, aynı ölçek",
        loc="left", fontsize=11, color="#0056a7",
    )
    map_axes.set_xlim(bounds.left, bounds.right)
    map_axes.set_ylim(bounds.bottom, bounds.top)
    map_axes.axis("off")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(args.output, dpi=110)
    print(f"  figure           {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
