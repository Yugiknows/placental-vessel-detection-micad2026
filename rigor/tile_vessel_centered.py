"""
tile_vessel_centered.py — the CORRECTED tiler. Vessel-centred, not sliding-window.

Replaces the whole-slide grid tiling that put the vessel on a tile EDGE in 58% of
positive tiles. This reuses the methodology from the repo's own
`prepare_cv_tiles.py` (vessel-centred crops, per-scale size gates, centre
dedup) — that is the trusted path; we do not reinvent it — and adds the two fixes
measured as necessary:

  * SNUG_FRAC: a vessel is only assigned to a scale whose tile can actually hold
    it with context (10x previously had NO upper cap but a 4096 l0px tile).
  * MIN_VISIBLE_FRAC: a neighbouring vessel is labelled only if enough of it is
    actually inside the tile (the grid tiler labelled 10% slivers).

Output is SLIDE-KEYED (one corpus, tiles named `{slide}_{scale}_{x}_{y}`), not
fold-keyed. LOSO folds are then *views* over this corpus, which is what makes the
C1 zero-overlap assertion checkable and means we never re-tile per fold.

Crash-safe: a (slide, scale) writes a completion marker only after it finishes,
and any partial output is purged before a retry. Two interruptions (a reboot and
a kill) already produced half-tiled slides that a naive "do tiles exist?" check
reported as complete.

    python tile_vessel_centered.py --dry-run
    python tile_vessel_centered.py --workers 8
"""

import argparse
import os
import random
import sys
import time
from multiprocessing import Pool, cpu_count

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tiling_config as TC

OUT_ROOT = r"C:\placenta_ssd\tiles_v3"          # SSD: D: is a spinning HDD
SLIDES_ROOT = r"C:\placenta_ssd\slides"


# ── one (slide, scale) unit ───────────────────────────────────────────────────

def extract_slide_scale(ndpi, ndpa, sid, scale, out_root, seed, dry_run):
    import numpy as np
    import openslide
    from prepare_training_tiles import parse_ndpa_bboxes

    g = TC.SCALE_GATES[scale]
    min_l0, max_l0 = g["min_l0_px"], g["max_l0_px"]

    slide = openslide.OpenSlide(ndpi)
    bboxes = parse_ndpa_bboxes(ndpa, slide)

    level = slide.get_best_level_for_downsample(g["downsample"])
    actual_ds = slide.level_downsamples[level]
    W0, H0 = slide.dimensions
    tile_l0 = TC.TILE_SIZE * actual_ds
    half_l0 = tile_l0 / 2.0
    snug_l0 = tile_l0 * TC.SNUG_FRAC

    pos_dir_i = os.path.join(out_root, f"training_data_{scale}", "positives", "images")
    pos_dir_l = os.path.join(out_root, f"training_data_{scale}", "positives", "labels")
    neg_dir_i = os.path.join(out_root, f"training_data_{scale}", "negatives", "images")
    neg_dir_l = os.path.join(out_root, f"training_data_{scale}", "negatives", "labels")
    if not dry_run:
        for d in (pos_dir_i, pos_dir_l, neg_dir_i, neg_dir_l):
            os.makedirs(d, exist_ok=True)

    seen = set()
    n_pos = 0
    occupied = []          # tile rects we used, so negatives avoid them

    for (bx1, by1, bx2, by2) in bboxes:
        v = max(bx2 - bx1, by2 - by1)
        if v < min_l0 or (max_l0 is not None and v > max_l0):
            continue
        # must fit with context; oversized vessels belong to a coarser scale
        if v > snug_l0:
            continue

        vcx, vcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
        tx1 = int(max(0, min(vcx - half_l0, W0 - tile_l0)))
        ty1 = int(max(0, min(vcy - half_l0, H0 - tile_l0)))

        snap = max(1, int(half_l0 / TC.CENTRE_SNAP_DIV))
        key = (tx1 // snap, ty1 // snap)
        if key in seen:
            continue
        seen.add(key)

        tx2, ty2 = tx1 + tile_l0, ty1 + tile_l0
        labels = []
        for (ax1, ay1, ax2, ay2) in bboxes:
            a = max(ax2 - ax1, ay2 - ay1)
            if a < min_l0 or (max_l0 is not None and a > max_l0):
                continue
            if ax2 <= tx1 or ax1 >= tx2 or ay2 <= ty1 or ay1 >= ty2:
                continue
            cx1, cy1 = max(ax1, tx1), max(ay1, ty1)
            cx2, cy2 = min(ax2, tx2), min(ay2, ty2)
            area = (ax2 - ax1) * (ay2 - ay1)
            vis = ((cx2 - cx1) * (cy2 - cy1)) / area if area > 0 else 0.0
            # the centred vessel is fully visible; this gates only neighbours
            if vis < TC.MIN_VISIBLE_FRAC:
                continue
            w = (cx2 - cx1) / tile_l0
            h = (cy2 - cy1) / tile_l0
            if w * TC.TILE_SIZE < TC.MIN_BOX_PX or h * TC.TILE_SIZE < TC.MIN_BOX_PX:
                continue
            labels.append(
                f"0 {((cx1+cx2)/2.0 - tx1)/tile_l0:.6f} "
                f"{((cy1+cy2)/2.0 - ty1)/tile_l0:.6f} {w:.6f} {h:.6f}")

        if not labels:
            continue

        occupied.append((tx1, ty1, tx2, ty2))
        fname = f"{sid}_{scale}_{int(tx1):07d}_{int(ty1):07d}"
        if not dry_run:
            img = slide.read_region((tx1, ty1), level,
                                    (TC.TILE_SIZE, TC.TILE_SIZE)).convert("RGB")
            img.save(os.path.join(pos_dir_i, fname + ".png"))
            with open(os.path.join(pos_dir_l, fname + ".txt"), "w") as fh:
                fh.write("\n".join(labels) + "\n")
        n_pos += 1

    # ── negatives: tissue tiles containing no vessel of ANY size ──────────────
    rng = random.Random(f"{sid}|{scale}|{seed}")
    n_neg = 0
    tries = 0
    want = min(TC.NEG_CAP, int(n_pos * TC.NEG_RATIO)) if n_pos else 0
    while n_neg < want and tries < want * 40:
        tries += 1
        tx1 = rng.randint(0, max(0, int(W0 - tile_l0)))
        ty1 = rng.randint(0, max(0, int(H0 - tile_l0)))
        tx2, ty2 = tx1 + tile_l0, ty1 + tile_l0
        # reject if ANY annotation (any size) overlaps -> a true negative
        if any(not (ax2 <= tx1 or ax1 >= tx2 or ay2 <= ty1 or ay1 >= ty2)
               for (ax1, ay1, ax2, ay2) in bboxes):
            continue
        if any(not (ox2 <= tx1 or ox1 >= tx2 or oy2 <= ty1 or oy1 >= ty2)
               for (ox1, oy1, ox2, oy2) in occupied):
            continue
        img = slide.read_region((tx1, ty1), level,
                                (TC.TILE_SIZE, TC.TILE_SIZE)).convert("RGB")
        if np.array(img).mean() > TC.WHITE_THRESH:      # blank glass, not tissue
            continue
        fname = f"{sid}_{scale}_{int(tx1):07d}_{int(ty1):07d}"
        if not dry_run:
            img.save(os.path.join(neg_dir_i, fname + ".png"))
            open(os.path.join(neg_dir_l, fname + ".txt"), "w").close()
        n_neg += 1

    slide.close()
    return n_pos, n_neg


# ── orchestration ─────────────────────────────────────────────────────────────

def marker(sid, scale, out_root):
    d = os.path.join(out_root, "_done")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{sid}__{scale}.done")


def purge(sid, scale, out_root):
    n = 0
    for split in ("positives", "negatives"):
        for kind, ext in (("images", ".png"), ("labels", ".txt")):
            d = os.path.join(out_root, f"training_data_{scale}", split, kind)
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.startswith(f"{sid}_{scale}_") and f.endswith(ext):
                    os.remove(os.path.join(d, f))
                    n += 1
    return n


def _worker(task):
    sid, ndpa, ndpi, scale, out_root, seed, dry = task
    t0 = time.time()
    try:
        p, n = extract_slide_scale(ndpi, ndpa, sid, scale, out_root, seed, dry)
        return (sid, scale, p, n, time.time() - t0, None)
    except Exception as exc:
        return (sid, scale, 0, 0, time.time() - t0, f"{type(exc).__name__}: {exc}")


def main():
    os.environ.setdefault("PLACENTA_SLIDES_ROOT", SLIDES_ROOT)
    from annotation_scale_report import discover_clean_sources
    from retile_clean import DEFAULT_SLIDES

    ap = argparse.ArgumentParser()
    ap.add_argument("--slides", nargs="*", default=DEFAULT_SLIDES)
    ap.add_argument("--scales", nargs="*", default=list(TC.ALL_SCALES))
    ap.add_argument("--out-root", default=OUT_ROOT)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=min(8, cpu_count()))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    sources = discover_clean_sources()
    bad = [s for s in args.slides if s not in sources or sources[s][1] is None]
    if bad:
        sys.exit(f"REFUSED: no audited-CLEAN .ndpa/.ndpi for {bad} (constraint C2)")

    tasks = []
    for sid in args.slides:
        ndpa, ndpi, _ = sources[sid]
        for sc in args.scales:
            if not args.force and not args.dry_run \
                    and os.path.exists(marker(sid, sc, args.out_root)):
                continue
            if not args.dry_run:
                k = purge(sid, sc, args.out_root)
                if k:
                    print(f"  purged {k} partial files: {sid} {sc}")
            tasks.append((sid, ndpa, ndpi, sc, args.out_root, args.seed, args.dry_run))

    if not tasks:
        print("nothing to do — all (slide, scale) pairs complete.")
        return

    print(f"{len(tasks)} tasks | {args.workers} workers | method={TC.METHOD}"
          f"{' | DRY RUN' if args.dry_run else ''}\n")
    t0 = time.time()
    tot_p = tot_n = 0
    with Pool(args.workers) as pool:
        for i, (sid, sc, p, n, dt, err) in enumerate(
                pool.imap_unordered(_worker, tasks), 1):
            if err:
                print(f"[{i}/{len(tasks)}] FAILED {sid} {sc}: {err}")
                continue
            if not args.dry_run:
                open(marker(sid, sc, args.out_root), "w").close()
            tot_p += p
            tot_n += n
            print(f"[{i}/{len(tasks)}] {sid:<22}{sc:>4}  pos={p:<5} neg={n:<4} "
                  f"({dt/60:.1f}m)")

    print(f"\nTOTAL positives={tot_p}  negatives={tot_n}  "
          f"in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
