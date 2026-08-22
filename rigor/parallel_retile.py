"""
parallel_retile.py — same tiling as retile_clean.py, but across all CPU cores.

WHY THIS EXISTS: tiling was running on ONE core. It is not GPU work — OpenSlide
decodes JPEG-compressed WSI regions off disk, so there is no tensor math for a
GPU to accelerate. The cost is ~20k read_region calls per slide at 40x. The fix
is parallelism: this box has 8 physical cores (Ryzen 7 7700, 31GB RAM), so we
run one (slide, scale) task per worker.

The per-task extraction calls prepare_training_tiles.extract_tiles_for_scale
UNCHANGED — identical algorithm, identical seed, therefore identical output to
the slides already tiled sequentially. Only the scheduling changed. That matters:
switching the tissue-check algorithm would have been faster still, but would
have made the remaining slides inconsistent with the ones already done.

    python parallel_retile.py --tasks-from-remaining     # auto: what's missing
    python parallel_retile.py --slides X --scales 40x
"""

import argparse
import os
import sys
import time
from multiprocessing import Pool, cpu_count

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT_ROOT_DEFAULT = r"D:\windows_gpu_migration\placenta_training_clean"


def _worker(task):
    """One (slide, scale) unit. Must be top-level for Windows spawn."""
    import openslide
    from prepare_training_tiles import parse_ndpa_bboxes, extract_tiles_for_scale

    sid, ndpa, ndpi, scale, out_root, seed = task
    t0 = time.time()
    try:
        slide = openslide.OpenSlide(ndpi)
        bboxes = parse_ndpa_bboxes(ndpa, slide)
        from retile_clean import scale_cfg_for
        cfg = scale_cfg_for(scale, out_root)
        n_train, n_val, n_neg = extract_tiles_for_scale(
            slide, bboxes, cfg, sid, False, seed)
        slide.close()
        return (sid, scale, n_train, n_val, n_neg, time.time() - t0, None)
    except Exception as exc:
        return (sid, scale, 0, 0, 0, time.time() - t0, str(exc))


def marker_path(sid, scale, out_root):
    d = os.path.join(out_root, "_done")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{sid}__{scale}.done")


def already_done(sid, scale, out_root):
    """Completion MARKER, not tile presence.

    Checking 'does any tile exist' is unsafe: a run killed or rebooted midway
    leaves a half-tiled slide that then gets skipped as 'done', silently
    producing an incomplete dataset. (This bit us twice.) A marker is written
    only after a task returns successfully, so a partial slide always re-runs.
    """
    return os.path.exists(marker_path(sid, scale, out_root))


def purge_partial(sid, scale, out_root):
    """Delete every tile of an unfinished (slide, scale) so it re-tiles cleanly."""
    n = 0
    base = os.path.join(out_root, f"training_data_{scale}")
    for split in ("train/positives", "train/negatives", "val"):
        for kind, ext in (("images", ".png"), ("labels", ".txt")):
            d = os.path.join(base, *split.split("/"), kind)
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.startswith(f"{sid}_{scale}_") and f.endswith(ext):
                    os.remove(os.path.join(d, f))
                    n += 1
    return n


def main():
    from annotation_scale_report import discover_clean_sources
    from retile_clean import DEFAULT_SLIDES, ALL_SCALES

    ap = argparse.ArgumentParser()
    ap.add_argument("--slides", nargs="*", default=DEFAULT_SLIDES)
    ap.add_argument("--scales", nargs="*", default=ALL_SCALES, choices=ALL_SCALES)
    ap.add_argument("--out-root", default=OUT_ROOT_DEFAULT)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=min(8, cpu_count()))
    ap.add_argument("--force", action="store_true",
                    help="re-tile even if output already exists")
    args = ap.parse_args()

    sources = discover_clean_sources()
    missing = [s for s in args.slides if s not in sources or sources[s][1] is None]
    if missing:
        sys.exit(f"REFUSED: no CLEAN .ndpa/.ndpi for {missing}")

    tasks = []
    for sid in args.slides:
        ndpa, ndpi, _ = sources[sid]
        for scale in args.scales:
            if not args.force and already_done(sid, scale, args.out_root):
                continue
            # No marker => this pair never finished. Clear any partial tiles a
            # killed/rebooted run left behind before re-tiling.
            n = purge_partial(sid, scale, args.out_root)
            if n:
                print(f"  purged {n} partial files from {sid} {scale}")
            tasks.append((sid, ndpa, ndpi, scale, args.out_root, args.seed))

    if not tasks:
        print("nothing to do — all requested (slide, scale) pairs already tiled.")
        return

    # Biggest jobs first so stragglers don't tail the run (40x is slowest).
    order = {"40x": 0, "20x": 1, "10x": 2, "5x": 3}
    tasks.sort(key=lambda t: order.get(t[3], 9))

    print(f"{len(tasks)} (slide, scale) tasks on {args.workers} workers "
          f"[{cpu_count()} logical cores]\n")
    t0 = time.time()
    done = 0
    with Pool(args.workers) as pool:
        for sid, scale, ntr, nv, nn, dt, err in pool.imap_unordered(_worker, tasks):
            done += 1
            if err:
                print(f"[{done}/{len(tasks)}] FAILED {sid} {scale}: {err}")
            else:
                # marker written ONLY on success -> safe resume after any crash
                open(marker_path(sid, scale, args.out_root), "w").close()
                print(f"[{done}/{len(tasks)}] {sid:<22}{scale:>4}  "
                      f"train={ntr:<5} val={nv:<4} neg={nn:<5} ({dt/60:.1f} min)")
    print(f"\nall tasks finished in {(time.time()-t0)/60:.1f} min wall-clock")


if __name__ == "__main__":
    main()
