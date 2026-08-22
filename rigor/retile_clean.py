"""
retile_clean.py — re-tile slides at 10x/20x/40x from AUDITED CLEAN .ndpa only.

This deliberately does NOT use prepare_training_tiles.py's hardcoded SLIDE_PAIRS
(which points at Mac SSD paths and several CONTAMINATED .ndpa — S.3152_26_A3FD_1
and the 10xv25 copies are all model-generated). Instead it drives the tiler's
own per-scale extraction with the CLEAN source map from contamination_audit, so
fabricated boxes cannot re-enter the corpus.

Output goes to a FRESH root (default placenta_training_clean/) — the existing
placenta_training/ is never touched. Each scale dir is labelImg-ready:
train/positives/{images,labels} + a classes.txt.

    python retile_clean.py --dry-run                 # counts only, no writes
    python retile_clean.py --slides S.2723_26_CFD_1  # one slide, real
    python retile_clean.py                            # all include+add slides
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openslide

from annotation_scale_report import discover_clean_sources, GATES
from prepare_training_tiles import parse_ndpa_bboxes, extract_tiles_for_scale
from slide_registry import SCALES

OUT_ROOT_DEFAULT = r"D:\windows_gpu_migration\placenta_training_clean"

# The slides to re-tile: 8 recovered/clean + 3 substantial new (from
# slides_clean.yaml include + candidate_add). Tiny (<=3 annot) slides omitted.
DEFAULT_SLIDES = [
    "S.2_723_26_A3_FD_1", "S.2016_26_A2_FD_1", "A2FD_1", "BFD_1",
    "S.3508_26_EFD_1", "S.2723_26_CFD_1",
    "A2FD_1_S.2058_26", "S.2723_26_A2_FD_1",           # recovered
    "S.3508_26_GFD_2", "S.2723_26_BFD_1", "S.2723_26_E_FD_1",  # new
]

# 5x uses ds=32 (native openslide level 5) so a 1024px tile spans 32768 level-0
# px — comfortably framing the 20000px upper gate without the clipping bug that
# ds=8 (span 8192) had. Grid tiling here (unlike the old vessel-centered 5x
# tiler) also yields negatives, matching the other three scales.
SCALE_DOWNSAMPLE = {"10x": 4.0, "20x": 2.0, "40x": 1.0, "5x": 32.0}
ALL_SCALES = ["10x", "20x", "40x", "5x"]


def scale_cfg_for(scale, out_root):
    lo, hi = GATES[scale]
    return {
        "name": scale,
        "downsample": SCALE_DOWNSAMPLE[scale],
        "min_l0_px": lo,
        "max_l0_px": hi,
        "out_dir": os.path.join(out_root, f"training_data_{scale}"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slides", nargs="*", default=None,
                    help="slide ids (default: the 11 include+add slides)")
    ap.add_argument("--scales", nargs="*", default=ALL_SCALES,
                    choices=ALL_SCALES)
    ap.add_argument("--out-root", default=OUT_ROOT_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    want = args.slides or DEFAULT_SLIDES
    sources = discover_clean_sources()

    # SAFETY: refuse any slide lacking a CLEAN audited source.
    missing = [s for s in want if s not in sources or sources[s][1] is None]
    if missing:
        sys.exit(f"REFUSED: no CLEAN .ndpa (or no .ndpi) for: {missing}\n"
                 "Every re-tiled slide must have an audited clean source.")

    print(f"{'slide':<22}{'scale':>6}{'train':>7}{'val':>6}{'neg':>6}  "
          f"({'DRY' if args.dry_run else 'WRITE'} -> {args.out_root})")
    print("-" * 70)

    grand = {"train": 0, "val": 0, "neg": 0}
    for sid in want:
        ndpa, ndpi, n = sources[sid]
        slide = openslide.OpenSlide(ndpi)
        bboxes = parse_ndpa_bboxes(ndpa, slide)
        stem = sid  # keep the canonical slide id as the tile filename prefix
        for scale in args.scales:
            cfg = scale_cfg_for(scale, args.out_root)
            n_train, n_val, n_neg = extract_tiles_for_scale(
                slide, bboxes, cfg, stem, args.dry_run, args.seed)
            grand["train"] += n_train
            grand["val"] += n_val
            grand["neg"] += n_neg
            print(f"{sid:<22}{scale:>6}{n_train:>7}{n_val:>6}{n_neg:>6}")
            if not args.dry_run:
                _write_classes(cfg["out_dir"])
        slide.close()

    print("-" * 70)
    print(f"{'TOTAL':<28}{grand['train']:>7}{grand['val']:>6}{grand['neg']:>6}")
    if not args.dry_run:
        print(f"\nReview in labelImg:\n  python rigor/open_labelimg.py "
              f"--dir \"{scale_cfg_for(args.scales[0], args.out_root)['out_dir']}\"")


def _write_classes(out_dir):
    for sub in ("train/positives/labels", "train/negatives/labels", "val/labels"):
        d = os.path.join(out_dir, sub)
        if os.path.isdir(d):
            with open(os.path.join(d, "classes.txt"), "w", encoding="utf-8") as fh:
                fh.write("blood_vessel\n")


if __name__ == "__main__":
    main()
