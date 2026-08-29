#!/usr/bin/env python3
"""Render a PNG of the depth GeoTIFF, so the result gets looked at.

Producing a raster is not the same as checking it. This draws the depth grid
over the model terrain and prints the numbers that describe it, which is how
the output was reviewed before delivery.

    python tools/preview.py OUTPUT/q50_depth.tif -o docs/q50_depth_preview.png

Needs matplotlib (requirements-dev.txt); the pipeline itself does not.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.plot import plotting_extent  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raster", type=Path, nargs="?", default=Path("OUTPUT/q50_depth.tif"))
    parser.add_argument("-o", "--output", type=Path, default=Path("docs/q50_depth_preview.png"))
    parser.add_argument("--terrain", type=Path, help="Optional terrain raster to draw underneath.")
    args = parser.parse_args()

    with rasterio.open(args.raster) as source:
        depth = source.read(1, masked=True).astype("float32").filled(np.nan)
        extent = plotting_extent(source)
        tags = source.tags()
        bounds = source.bounds
        resolution = source.res[0]

    finite = np.isfinite(depth)
    print(f"{args.raster}")
    print(f"  grid        {depth.shape[1]} x {depth.shape[0]} @ {resolution:g} m")
    print(f"  extent      {bounds.left:.1f}, {bounds.bottom:.1f} .. {bounds.right:.1f}, {bounds.top:.1f}")
    print(f"  wet pixels  {finite.sum()} ({100 * finite.mean():.1f}% of the grid)")
    print(f"  wet area    {finite.sum() * resolution ** 2:,.0f} m2")
    if finite.any():
        print(f"  depth       max {np.nanmax(depth):.3f} m, mean {np.nanmean(depth):.3f} m")
        print(f"  percentiles {np.nanpercentile(depth, [50, 90, 99]).round(3).tolist()} m (50/90/99)")
    for key in ("SCENARIO", "PLAN_NUMBER", "PLAN_TITLE", "PLAN_SHORT_ID", "SIMULATION_WINDOW"):
        if key in tags:
            print(f"  {key.lower():<11} {tags[key]}")

    figure, (map_axes, hist_axes) = plt.subplots(
        1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [2.2, 1]}
    )

    if args.terrain and args.terrain.exists():
        with rasterio.open(args.terrain) as terrain_source:
            window = rasterio.windows.from_bounds(*bounds, transform=terrain_source.transform)
            ground = terrain_source.read(
                1, window=window, out_shape=depth.shape, boundless=True, fill_value=np.nan
            )
        ground = np.where(ground < -9000, np.nan, ground)
        map_axes.imshow(ground, extent=extent, cmap="Greys_r", alpha=0.85)

    image = map_axes.imshow(depth, extent=extent, cmap="YlGnBu", vmin=0)
    figure.colorbar(image, ax=map_axes, label="maximum depth (m)", shrink=0.85)
    map_axes.set_title(
        f"{tags.get('SCENARIO', '?')} maximum water depth  "
        f"(plan {tags.get('PLAN_NUMBER', '?')}, {tags.get('PLAN_TITLE', '?')})"
    )
    map_axes.set_xlabel("easting (m)")
    map_axes.set_ylabel("northing (m)")
    map_axes.ticklabel_format(style="plain")

    hist_axes.hist(depth[finite], bins=60, color="#2b6cb0")
    hist_axes.set_yscale("log")
    hist_axes.set_title("depth distribution")
    hist_axes.set_xlabel("depth (m)")
    hist_axes.set_ylabel("pixels (log)")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(args.output, dpi=110)
    print(f"  preview     {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
