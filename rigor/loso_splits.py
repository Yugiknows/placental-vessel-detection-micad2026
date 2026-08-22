"""
loso_splits.py — leave-one-slide-out fold generator (constraints C1 + C4).

For N ratified clean slides this emits N folds, each holding out exactly one
slide for evaluation. Every fold is checked with a hard assertion that the
train and eval tile sets share ZERO slide IDs — the check runs on the actual
tile filenames, not on the intended slide lists, so a mis-parsed filename or a
stray tile cannot slip through.

Two modes:

    python loso_splits.py --preview   # feasibility report; writes nothing,
                                      # runs on the UNRATIFIED allow-list
    python loso_splits.py --write     # emits splits; requires ratification

--preview exists because the LOSO design has to be checked for viability
BEFORE anyone commits to a slide list: a held-out slide with zero positive
tiles at some scale makes per-slide AP undefined for that (fold, scale), and a
slide with a handful of tiles makes it uselessly noisy. Better to see that now
than after 12 training runs.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
from slide_registry import SCALES, AllowListError, load_clean_slides, load_raw
from tiling_fingerprint import slide_of

DATA_ROOT = paths.PLACENTA_TRAINING
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "splits")

# A held-out slide with fewer than this many positive tiles yields a per-slide
# AP too noisy to enter a paired test. Flagged, not silently dropped.
MIN_EVAL_TILES = 10


def index_tiles(data_root=DATA_ROOT, scales=SCALES):
    """-> {scale: {slide: {"pos": [paths], "neg": [paths]}}} over label files."""
    index = {}
    for scale in scales:
        root = os.path.join(data_root, f"training_data_{scale}")
        per_slide = {}
        for dirpath, _, files in os.walk(root):
            norm = dirpath.replace("\\", "/")
            if "/negatives" in norm:
                kind = "neg"
            elif "/positives" in norm or "/val" in norm or "/test" in norm:
                kind = "pos"
            else:
                continue
            if not norm.endswith("/labels") and "/labels" not in norm:
                continue
            for f in sorted(files):
                if f.startswith("._") or f == "classes.txt" or not f.endswith(".txt"):
                    continue
                slide = slide_of(f, scale)
                if slide is None:
                    continue
                bucket = per_slide.setdefault(slide, {"pos": [], "neg": []})
                bucket[kind].append(os.path.join(dirpath, f))
        index[scale] = per_slide
    return index


def feasibility(slides, index):
    """Per (slide, scale) positive-tile counts + LOSO viability verdicts."""
    rows, problems = [], []
    for slide in slides:
        row = {"slide": slide}
        for scale in SCALES:
            n = len(index[scale].get(slide, {}).get("pos", []))
            row[scale] = n
            if n == 0:
                problems.append(
                    f"{slide} @ {scale}: ZERO positive tiles — per-slide AP is "
                    f"UNDEFINED for this fold/scale. The per_mag_3x arm cannot "
                    f"be scored on this held-out slide."
                )
            elif n < MIN_EVAL_TILES:
                problems.append(
                    f"{slide} @ {scale}: only {n} positive tiles — per-slide AP "
                    f"will be extremely noisy (< {MIN_EVAL_TILES})."
                )
        rows.append(row)
    return rows, problems


def build_folds(slides, index):
    folds = []
    for i, held_out in enumerate(sorted(slides)):
        train_slides = sorted(s for s in slides if s != held_out)
        fold = {
            "fold": i,
            "held_out_slide": held_out,
            "train_slides": train_slides,
            "scales": {},
        }
        for scale in SCALES:
            eval_tiles = index[scale].get(held_out, {}).get("pos", [])
            train_pos, train_neg = [], []
            for s in train_slides:
                b = index[scale].get(s, {"pos": [], "neg": []})
                train_pos += b["pos"]
                train_neg += b["neg"]
            fold["scales"][scale] = {
                "n_eval_pos": len(eval_tiles),
                "n_train_pos": len(train_pos),
                "n_train_neg": len(train_neg),
            }
            assert_zero_slide_overlap(scale, train_pos + train_neg, eval_tiles, fold)
        folds.append(fold)
    return folds


def assert_zero_slide_overlap(scale, train_paths, eval_paths, fold):
    """Constraint C1, enforced on real filenames. Raises on any shared slide."""
    tr = {slide_of(os.path.basename(p), scale) for p in train_paths}
    ev = {slide_of(os.path.basename(p), scale) for p in eval_paths}
    tr.discard(None)
    ev.discard(None)

    shared = tr & ev
    if shared:
        raise AssertionError(
            f"C1 VIOLATION in fold {fold['fold']} @ {scale}: slides appear in "
            f"BOTH train and eval: {sorted(shared)}"
        )
    if ev and ev != {fold["held_out_slide"]}:
        raise AssertionError(
            f"C1 VIOLATION in fold {fold['fold']} @ {scale}: eval set contains "
            f"slides other than the held-out one: {sorted(ev)}"
        )
    return True


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--preview", action="store_true",
                   help="feasibility report only; writes nothing; ignores ratification")
    g.add_argument("--write", action="store_true",
                   help="emit split files; REQUIRES a ratified allow-list")
    args = ap.parse_args()

    if args.preview:
        doc = load_raw()
        slides = doc.get("include") or []
        print("*** PREVIEW — allow-list is NOT ratified; writing nothing. ***\n")
    else:
        try:
            slides = load_clean_slides()
        except AllowListError as exc:
            print(exc, file=sys.stderr)
            return 2

    index = index_tiles()
    rows, problems = feasibility(slides, index)

    print(f"LOSO over {len(slides)} clean slides -> {len(slides)} folds\n")
    print(f"{'slide':<24}" + "".join(f"{s:>8}" for s in SCALES) + f"{'total':>8}")
    print("-" * 56)
    for r in rows:
        tot = sum(r[s] for s in SCALES)
        print(f"{r['slide']:<24}" + "".join(f"{r[s]:>8}" for s in SCALES) + f"{tot:>8}")
    print("-" * 56)
    print(f"{'TOTAL':<24}" + "".join(
        f"{sum(r[s] for r in rows):>8}" for s in SCALES))

    if problems:
        print("\n!! LOSO FEASIBILITY PROBLEMS (positive tiles per held-out slide):")
        for p in problems:
            print(f"   - {p}")

    folds = build_folds(slides, index)
    print(f"\nC1 zero-overlap assertion passed for all {len(folds)} folds x {len(SCALES)} scales.")

    if args.preview:
        print("\nPreview only. Ratify rigor/slides_clean.yaml, then rerun with --write.")
        return 1 if problems else 0

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "loso_folds.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"slides": slides, "folds": folds}, fh, indent=2)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
