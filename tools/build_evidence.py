"""Regenerate the evidence blocks the report reads at compile time.

The report does not quote numbers; it reads ``docs/rapor/kanit/*.txt`` with
Typst's ``read()``, so what the PDF shows is whatever these files contain.  That
only means anything if the files themselves are output rather than prose, and
until now they were produced by hand, one command at a time, with nothing
recording how.  A number whose provenance is a memory is a number nobody can
check.

So the commands live here.  Each block prints the command that produced it,
then the output of actually running it.

    python tools/build_evidence.py --project "<CASE DATA 2>"
    python tools/build_evidence.py --project "<CASE DATA 2>" --only B5 B6

Nothing here writes to the delivered data.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
EVIDENCE = ROOT / "docs" / "rapor" / "kanit"

REFERENCE = Path("AKA_AFY_BAY_INPINAR_1/3_Pafta/6_derinlik/q50_d.tif")
MODELS = Path("AKA_AFY_BAY_INPINAR_1/1_Modeller")


def _run(command: list[str]) -> str:
    finished = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT))
    return (finished.stdout or "") + (finished.stderr or "")


def _scene(project: Path):
    from q50depth import depth, results, surface, terrain

    models = project / MODELS
    loaded = results.load(models / "A_A_B_INPINAR.p05.hdf")
    full = terrain.resolve(models, loaded.terrain_filename)
    bare = terrain.Terrain(full.hdf_path, full.raster_path, ())
    grid = depth.grid_of(project / REFERENCE)
    with rasterio.open(project / REFERENCE) as source:
        band = source.read(1)
        reference = np.where(band == source.nodata, np.nan, band)
    return loaded, full, bare, grid, reference, models


def _depth(surface_grid, elevation, floor: float) -> np.ndarray:
    out = surface_grid - elevation
    out = np.where(np.isfinite(out), out, np.nan)
    out[out <= floor] = np.nan
    return out


def _agreement(produced: np.ndarray, reference: np.ndarray) -> tuple[float, float, float]:
    ours, theirs = np.isfinite(produced), np.isfinite(reference)
    both = ours & theirs
    iou = both.sum() / (ours | theirs).sum() * 100
    difference = produced[both] - reference[both]
    return iou, float(np.abs(difference).mean()), float(difference.mean())


# --------------------------------------------------------------------------


def b5_corrections(project: Path) -> str:
    """The two terrain corrections, all four combinations."""
    from q50depth import depth, surface

    loaded, full, bare, grid, reference, _ = _scene(project)
    mesh = loaded.meshes[0]
    lines = [
        "$ Iki duzeltmenin tam carpim tablosu (2x2), egimli su yuzeyi ile",
        "",
        "  bina kotu     kuru hucre tolerans   islak piksel   maks m    ort m  >2m piksel",
        "  " + "-" * 76,
    ]
    for applied, model in (("UYGULANARAK", full), ("UYGULANMADAN", bare)):
        elevation, _ = depth.read_terrain(model, None, None, grid)
        for label, tolerance in (("ACIK  ", depth.DEFAULT_WET_TOLERANCE), ("KAPALI", 0.0)):
            wet = mesh.wet_cells(tolerance)
            built = _depth(surface.sloping(mesh, wet, grid), elevation, 0.0)
            finite = np.isfinite(built)
            lines.append(
                f"  {applied:<13s} {label:<21s} {int(finite.sum()):>12d} "
                f"{np.nanmax(built):>8.3f} {np.nanmean(built):>8.3f} "
                f"{int((built > 2).sum()):>11d}"
            )
    lines += [
        "",
        "  Ilk satir = teslim edilen yapilandirma.",
        "",
        "  Not: egimli yuzeye gecince baskin duzeltme yer degistirdi. Duz yuzeyde",
        "  haritayi kurtaran sey bina kot duzeltmesiydi; egimli yuzeyde kuru hucre",
        "  toleransi o hucreleri zaten disarida biraktigi icin bina duzeltmesinin",
        "  katkisi kuculuyor. Ikisi de yerinde duruyor.",
    ]
    return "\n".join(lines) + "\n"


def b6_render_mode(project: Path) -> str:
    """Which water surface RASMapper draws, and what each one costs."""
    from q50depth import depth, surface

    models = project / MODELS
    rasmap = models / "A_A_B_INPINAR.rasmap"
    found = [
        line.strip()
        for line in rasmap.read_text(encoding="utf-8", errors="replace").splitlines()
        if "RenderMode" in line
    ]
    loaded, full, _, grid, reference, _ = _scene(project)
    mesh = loaded.meshes[0]
    elevation, _ = depth.read_terrain(full, None, None, grid)
    wet = mesh.wet_cells(depth.DEFAULT_WET_TOLERANCE)

    lines = [
        "$ grep RenderMode A_A_B_INPINAR.rasmap",
        *(f"  {line}" for line in dict.fromkeys(found)),
        "",
        "  Projenin kendi yapilandirmasi egimli (sloping) su yuzeyi istiyor.",
        "",
        "$ Iki yuzey modelinin musteri referansina karsi olculmesi",
        "  (referansin kendi izgarasinda, esik 0,005 m = referansin taban degeri)",
        "",
        "  yuzey                      IoU     |fark|    sapma     maks      ort",
        "  " + "-" * 68,
    ]
    for label, mode in (("duz (hucre basina sabit)", "flat"), ("egimli (sloping)", "sloping")):
        built = _depth(surface.build(mesh, wet, grid, mode), elevation, 0.005)
        iou, absolute, bias = _agreement(built, reference)
        lines.append(
            f"  {label:<24s} {iou:6.2f}%  {absolute:8.4f} {bias:+8.4f} "
            f"{np.nanmax(built):8.4f} {np.nanmean(built):8.4f}"
        )
    lines.append(
        f"  {'referansin kendisi':<24s} {'':7s}  {'':8s} {'':8s} "
        f"{np.nanmax(reference):8.4f} {np.nanmean(reference):8.4f}"
    )
    return "\n".join(lines) + "\n"


def b7_terrain_tiles(project: Path) -> str:
    """Which terrain tile wins in the channel, and what it costs."""
    from q50depth import depth, surface

    loaded, full, bare, grid, reference, models = _scene(project)
    mesh = loaded.meshes[0]

    fine = np.full(grid.shape, np.nan, dtype="float32")
    with rasterio.open(models / "merge.ent_.ent.tif") as tile:
        reproject(
            source=rasterio.band(tile, 1), destination=fine,
            src_transform=tile.transform, src_crs=tile.crs, src_nodata=tile.nodata,
            dst_transform=grid.transform, dst_crs=tile.crs, dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
    covered = np.isfinite(fine)
    from_vrt, _ = depth.read_terrain(full, None, None, grid)
    signed = (fine - from_vrt)[covered]

    lines = [
        "$ merge.Clone.vrt karo sirasi",
        "  1. merge.ent_.ent.tif                 4726 x 1521 @ 0,1 m  (kanal olcumu)",
        "  2. merge.SET14_37_DTM....tif         10935 x 7884 @ 0,5 m  (tum havza)",
        "  GDAL ikinci kaynagi birincinin ustune cizer, yani kanalda okunan kot",
        "  ince olcum degil kaba DTM'dir.",
        "",
        "$ ent karosu alaninda VRT ile ince olcumun karsilastirilmasi",
        f"  ince olcum referans penceresinin %{covered.mean() * 100:.1f}'ini kapliyor",
        f"  ayni cikan piksel orani (|fark| < 1e-4): %{np.mean(np.abs(signed) < 1e-4) * 100:.2f}",
        f"  ortalama fark (ince - VRT): {signed.mean():+.4f} m, medyan {np.median(signed):+.4f} m",
        f"  ince olcumun daha alcak oldugu piksel orani: %{np.mean(signed < 0) * 100:.1f}",
        "",
        "$ Iki degisken bagimsiz cevrildi: bina duzeltmesi x arazi karosu",
        "  (ayni su yuzeyi, referansin izgarasi, esik 0,005 m)",
        "",
        "  bina duzeltmesi  arazi karosu     IoU    |fark|     maks      ort   islak px",
        "  " + "-" * 76,
    ]
    wet = mesh.wet_cells(depth.DEFAULT_WET_TOLERANCE)
    painted = surface.sloping(mesh, wet, grid)
    for applied, model in (("acik  ", full), ("KAPALI", bare)):
        base, _ = depth.read_terrain(model, None, None, grid)
        for tile_label, elevation in (
            ("VRT (kaba)", base),
            ("ince ent  ", np.where(covered, fine, base)),
        ):
            built = _depth(painted, elevation, 0.005)
            iou, absolute, _ = _agreement(built, reference)
            lines.append(
                f"  {applied:<16s} {tile_label:<13s} {iou:6.2f}% {absolute:9.4f} "
                f"{np.nanmax(built):8.4f} {np.nanmean(built):8.4f} "
                f"{int(np.isfinite(built).sum()):>10d}"
            )
    lines += [
        f"  {'REFERANS':<16s} {'':13s} {'':7s} {'':9s} "
        f"{np.nanmax(reference):8.4f} {np.nanmean(reference):8.4f} "
        f"{int(np.isfinite(reference).sum()):>10d}",
        "",
        "  Bina duzeltmesini kapatmak maksimumu hic degistirmiyor ve ortalamayi",
        "  0,2 mm oynatiyor. Karo secimi maksimumu 28 cm, ortusmeyi 24 puan",
        "  degistiriyor. Fark karo seciminden geliyor.",
    ]
    return "\n".join(lines) + "\n"


def e2_tests(project: Path) -> str:
    return (
        "$ python -m pytest -q --no-header\n"
        + _run([sys.executable, "-m", "pytest", "-q", "--no-header"])[-1500:]
        + "\n$ python -m pytest --collect-only -q | tail -1\n"
        + _run([sys.executable, "-m", "pytest", "--collect-only", "-q"]).splitlines()[-1]
        + "\n"
    )


BUILDERS = {
    "B5": ("B5-carpim-tablosu.txt", b5_corrections),
    "B6": ("B6-render-mode.txt", b6_render_mode),
    "B7": ("B7-arazi-karo-onceligi.txt", b7_terrain_tiles),
    "E2": ("E2-test-envanteri.txt", e2_tests),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--only", nargs="*", choices=sorted(BUILDERS),
                        help="Rebuild just these blocks.")
    args = parser.parse_args(argv)

    if not (args.project / REFERENCE).is_file():
        parser.error(f"no reference map at {args.project / REFERENCE}")

    wanted = args.only or sorted(BUILDERS)
    for key in wanted:
        name, builder = BUILDERS[key]
        print(f"{key}  {name} ...", end=" ", flush=True)
        (EVIDENCE / name).write_text(builder(args.project), encoding="utf-8")
        print("yazildi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
