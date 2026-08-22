"""
annotation_scale_report.py — does each slide's ground truth actually populate
the 10x / 20x / 40x scales?

A vessel only produces a tile at a given scale if its FULL size (max of width,
height, in level-0 px) falls inside that scale's gate:

    40x : 15   .. 450        (small capillaries)
    20x : 100  .. 1200       (medium)
    10x : 450  .. inf        (large, catch-all)
    5x  : 2400 .. 20000      (giant)

The gates OVERLAP, so one vessel can legitimately feed several scales. This
report parses each slide's CLEAN .ndpa (auto-discovered + audited), converts to
level-0 boxes with the repo's own Hamamatsu-offset logic, and counts how many
annotations qualify per scale. That tells us, per slide, whether re-tiling at
10x/20x/40x would yield data — and how much n we can rebuild.

Only CLEAN .ndpa are used (contamination_audit). Requires openslide + the raw
slides (now present under D:\PLACENTA SLIDES).
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openslide

from contamination_audit import audit_ndpa
from prepare_training_tiles import parse_ndpa_bboxes

# Override with PLACENTA_SLIDES_ROOT to read from the NVMe SSD staging copy
# (D: is a spinning HDD — see rigor/stage_to_ssd.py for why that matters).
SLIDES_ROOT = os.environ.get("PLACENTA_SLIDES_ROOT", r"D:\PLACENTA SLIDES")

# (min_l0, max_l0 or None) — must match prepare_training_tiles SCALE_CONFIGS
# and prepare_5x_tiles.
GATES = {
    "40x": (15, 450),
    "20x": (100, 1200),
    "10x": (450, None),
    "5x": (2400, 20000),
}

# Ignore obvious inference-dump trees; we want slide-side annotation sources.
SKIP_DIR_MARKERS = ("annotaions", "runs", "predict")


def stem_of(ndpa_path):
    b = os.path.basename(ndpa_path)
    for suf in (".ndpi.ndpa", ".ndpa"):
        if b.endswith(suf):
            b = b[: -len(suf)]
            break
    return b


def slide_id(stem):
    return stem.replace(" ", "_")


def discover_clean_sources(root=SLIDES_ROOT):
    """-> {slide_id: (ndpa_path, ndpi_path, n_annots)} richest clean source each."""
    ndpi_by_stem = {}
    clean = {}
    for dirpath, _, files in os.walk(root):
        low = dirpath.lower()
        if any(m in low for m in SKIP_DIR_MARKERS):
            continue
        for f in files:
            if f.startswith("._"):
                continue
            full = os.path.join(dirpath, f)
            if f.lower().endswith(".ndpi"):
                ndpi_by_stem.setdefault(os.path.splitext(f)[0], full)
            elif f.lower().endswith(".ndpa"):
                verdict, d = audit_ndpa(full)
                if verdict != "CLEAN":
                    continue
                stem = stem_of(full)
                prev = clean.get(stem)
                if prev is None or d["n_annotations"] > prev[2]:
                    clean[stem] = (full, None, d["n_annotations"])

    # attach a matching .ndpi per clean stem
    out = {}
    for stem, (ndpa, _, n) in clean.items():
        ndpi = ndpi_by_stem.get(stem)
        out[slide_id(stem)] = (ndpa, ndpi, n)
    return out


def bucket_sizes(ndpi, ndpa):
    slide = openslide.OpenSlide(ndpi)
    boxes = parse_ndpa_bboxes(ndpa, slide)
    slide.close()
    sizes = [max(x2 - x1, y2 - y1) for x1, y1, x2, y2 in boxes]
    counts = {}
    for scale, (lo, hi) in GATES.items():
        counts[scale] = sum(1 for s in sizes if s >= lo and (hi is None or s <= hi))
    return sizes, counts


def main():
    # Slides already excluded as contaminated (per slides_clean.yaml).
    contaminated = {
        "S.3152_26_A3FD_1", "A3_FD_1", "A2FD_1_S.2058_26",
        "S.2016_26_A3_FD_1", "S.2723_26_A2_FD_1",
    }
    original12 = {
        "S.3152_26_A3FD_1", "S.2_723_26_A3_FD_1", "A3_FD_1", "A2FD_1_S.2058_26",
        "S.2723_26_A2_FD_1", "S.2016_26_A2_FD_1", "A2FD_1", "S.3508_26_JFD_2",
        "BFD_1", "S.3508_26_EFD_1", "S.2016_26_A3_FD_1", "S.2723_26_CFD_1",
    }

    sources = discover_clean_sources()
    print(f"Clean annotation sources found: {len(sources)} slides\n")

    hdr = f"{'slide':<22}{'annots':>7}{'40x':>6}{'20x':>6}{'10x':>6}{'5x':>6}  status"
    print(hdr)
    print("-" * len(hdr))

    totals = defaultdict(int)
    grid_ok = []
    for sid in sorted(sources):
        ndpa, ndpi, n = sources[sid]
        if ndpi is None:
            print(f"{sid:<22}{n:>7}  {'':>24}  NO .ndpi on disk — cannot tile")
            continue
        try:
            _, c = bucket_sizes(ndpi, ndpa)
        except Exception as exc:
            print(f"{sid:<22}{n:>7}  ERROR: {exc}")
            continue

        if sid in contaminated:
            status = "RECOVERED (was excluded)"
        elif sid not in original12:
            status = "NEW slide"
        else:
            status = "clean (in corpus)"

        grid = c["10x"] + c["20x"] + c["40x"]
        if grid > 0:
            grid_ok.append(sid)
        for k in GATES:
            totals[k] += c[k]
        print(f"{sid:<22}{n:>7}{c['40x']:>6}{c['20x']:>6}{c['10x']:>6}{c['5x']:>6}  {status}")

    print("-" * len(hdr))
    print(f"{'TOTAL':<22}{'':>7}{totals['40x']:>6}{totals['20x']:>6}"
          f"{totals['10x']:>6}{totals['5x']:>6}")
    print(f"\nSlides that yield >=1 core-grid (10x/20x/40x) annotation: "
          f"{len(grid_ok)}")
    print("These are the LOSO units available if re-tiled from clean source.")


if __name__ == "__main__":
    main()
