"""Measure a produced depth grid against a reference depth grid.

The client's delivery carries its own depth maps, produced from this model in
RASMapper and then finished in a GIS (``3_Pafta/6_derinlik/q50_d.tif`` and the
identical copy at ``3_Pafta/q50_d.tif``).  They are the thing the output has to
agree with, so agreement has to be a number, not an impression.

What is reported, and why each one:

wet area
    How much ground each map calls wet.  The headline number is the
    intersection over union of the two wet areas: 100% would mean the same
    ground, pixel for pixel.

depth where both are wet
    Mean absolute difference, RMS, and bias.  The bias matters on its own: a
    map can disagree about the edge and still have the water surface right,
    and that is a different kind of error from one that is deep or shallow
    everywhere.

boundary tolerance
    The reference grid does not sit on the terrain's pixel boundaries -- it
    was resampled at some point, and its origin is half a pixel off ours -- so
    a strip along every flood edge disagrees for reasons that are not physics.
    Repeating the count while allowing a 1 and 2 pixel slack separates that
    from real disagreement.

Usage:
    python tools/compare_reference.py OUTPUT/q50_depth.tif REFERENCE.tif \
        [--png comparison.png]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject


def _load(path: Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as source:
        band = source.read(1).astype("float32")
        if source.nodata is not None:
            band = np.where(band == np.float32(source.nodata), np.nan, band)
        return band, {
            "transform": source.transform,
            "crs": source.crs,
            "width": source.width,
            "height": source.height,
        }


def _onto(band: np.ndarray, source: dict, target: dict) -> np.ndarray:
    """Nearest-neighbour resample onto the target grid.

    Nearest, not bilinear: the question is which pixels are wet, and averaging
    a wet pixel with a dry one invents a depth that neither map claims.
    """
    out = np.full((target["height"], target["width"]), np.nan, dtype="float32")
    reproject(
        source=band,
        destination=out,
        src_transform=source["transform"],
        src_crs=source["crs"] or target["crs"],
        src_nodata=np.nan,
        dst_transform=target["transform"],
        dst_crs=target["crs"],
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    return out


def _dilate(mask: np.ndarray, steps: int) -> np.ndarray:
    """Grow a mask by ``steps`` pixels in all eight directions.

    Written out with array shifts so the tool needs nothing beyond numpy.
    """
    grown = mask.copy()
    for _ in range(steps):
        padded = np.pad(grown, 1, constant_values=False)
        grown = np.zeros_like(grown)
        for row in (0, 1, 2):
            for col in (0, 1, 2):
                grown |= padded[row : row + mask.shape[0], col : col + mask.shape[1]]
    return grown


def compare(ours_path: Path, reference_path: Path, png: Path | None = None) -> dict:
    ours, ours_grid = _load(ours_path)
    reference, reference_grid = _load(reference_path)

    print(f"produced   {ours_path}")
    print(f"           {ours_grid['width']} x {ours_grid['height']} @ "
          f"{ours_grid['transform'].a:g} m, origin "
          f"({ours_grid['transform'].c:.4f}, {ours_grid['transform'].f:.4f})")
    print(f"reference  {reference_path}")
    print(f"           {reference_grid['width']} x {reference_grid['height']} @ "
          f"{reference_grid['transform'].a:g} m, origin "
          f"({reference_grid['transform'].c:.4f}, {reference_grid['transform'].f:.4f})")

    same_grid = (
        ours_grid["width"] == reference_grid["width"]
        and ours_grid["height"] == reference_grid["height"]
        and np.allclose(
            list(ours_grid["transform"])[:6], list(reference_grid["transform"])[:6]
        )
    )
    if same_grid:
        print("           the two grids are identical; no resampling needed")
        aligned = ours
    else:
        offset_x = reference_grid["transform"].c - ours_grid["transform"].c
        offset_y = reference_grid["transform"].f - ours_grid["transform"].f
        print(f"           grids differ; reference origin is offset by "
              f"({offset_x:+.4f}, {offset_y:+.4f}) m "
              f"({offset_x / ours_grid['transform'].a:+.2f}, "
              f"{offset_y / ours_grid['transform'].a:+.2f} pixels). "
              "Resampling ours onto it (nearest).")
        aligned = _onto(ours, ours_grid, reference_grid)

    ours_wet = np.isfinite(aligned)
    reference_wet = np.isfinite(reference)
    both = ours_wet & reference_wet
    union = ours_wet | reference_wet

    print()
    print("wet area")
    print(f"  produced          {int(ours_wet.sum()):>9,} px"
          f"  ({ours_wet.sum() * abs(reference_grid['transform'].a) ** 2:,.0f} m2)")
    print(f"  reference         {int(reference_wet.sum()):>9,} px"
          f"  ({reference_wet.sum() * abs(reference_grid['transform'].a) ** 2:,.0f} m2)")
    print(f"  shared            {int(both.sum()):>9,} px")
    print(f"  only produced     {int((ours_wet & ~reference_wet).sum()):>9,} px")
    print(f"  only reference    {int((reference_wet & ~ours_wet).sum()):>9,} px")
    iou = both.sum() / union.sum() if union.any() else 0.0
    print(f"  agreement (IoU)   {iou * 100:>8.2f} %")

    print()
    print("boundary tolerance (how much of the disagreement is grid alignment)")
    for slack in (0, 1, 2):
        if slack == 0:
            extra = int((ours_wet & ~reference_wet).sum())
            missing = int((reference_wet & ~ours_wet).sum())
        else:
            extra = int((ours_wet & ~_dilate(reference_wet, slack)).sum())
            missing = int((reference_wet & ~_dilate(ours_wet, slack)).sum())
        print(f"  within {slack} px       only produced {extra:>8,}   "
              f"only reference {missing:>8,}   total {extra + missing:>8,}")

    stats: dict = {"iou": float(iou)}
    if both.any():
        difference = aligned[both] - reference[both]
        print()
        print("depth where both are wet")
        print(f"  mean absolute     {np.abs(difference).mean():>8.4f} m")
        print(f"  RMS               {np.sqrt((difference ** 2).mean()):>8.4f} m")
        print(f"  bias (ours-ref)   {difference.mean():>+8.4f} m")
        print(f"  within 0.01 m     {np.mean(np.abs(difference) < 0.01) * 100:>8.2f} %")
        print(f"  within 0.05 m     {np.mean(np.abs(difference) < 0.05) * 100:>8.2f} %")
        stats.update(
            mean_absolute=float(np.abs(difference).mean()),
            rms=float(np.sqrt((difference ** 2).mean())),
            bias=float(difference.mean()),
        )

    print()
    print("depth range")
    for label, band in (("produced", aligned), ("reference", reference)):
        finite = band[np.isfinite(band)]
        if finite.size:
            print(f"  {label:<10}      min {finite.min():.4f}   max {finite.max():.4f}   "
                  f"mean {finite.mean():.4f} m")

    if png is not None:
        _write_png(ours_wet, reference_wet, png)
        print()
        print(f"comparison image  {png}")
        print("  blue = both wet, red = only produced, green = only reference")

    return stats


def _write_png(ours_wet: np.ndarray, reference_wet: np.ndarray, path: Path) -> None:
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        print("  (Pillow is not installed; skipping the image)", file=sys.stderr)
        return
    height, width = ours_wet.shape
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    canvas[ours_wet & reference_wet] = (40, 90, 200)
    canvas[ours_wet & ~reference_wet] = (220, 40, 40)
    canvas[~ours_wet & reference_wet] = (30, 170, 60)
    Image.fromarray(canvas).save(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("produced", type=Path, help="The depth GeoTIFF this project wrote.")
    parser.add_argument("reference", type=Path, help="The client's depth GeoTIFF.")
    parser.add_argument("--png", type=Path, help="Write a wet-area comparison image here.")
    args = parser.parse_args(argv)
    for path in (args.produced, args.reference):
        if not path.is_file():
            parser.error(f"no such file: {path}")
    compare(args.produced, args.reference, args.png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
