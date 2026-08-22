"""
backup.py — snapshot the irreplaceable artefacts.

WHAT IS IRREPLACEABLE (and why):
  * tiles_v3 positives  — the user hand-reviewed EVERY one in labelImg (566/756 of
    the 10x labels were edited, tiles were deleted). Regenerating from the .ndpa
    would silently discard all of that.
  * tiles_v3 negatives  — hand-culled the same way, on top of a 43k-candidate
    screening pass that took over an hour of GPU.
  * the 5x negatives    — could not be reproduced by thresholding at all (only 2
    survived); they exist only because we ranked and the user verified them.
  * slides_clean.yaml   — the ratified clean-slide list (constraint C2).
  * splits_v3/          — the LOSO folds + the image lists ultralytics reads.
  * screener weights    — 40 min of training; the negatives depend on it.

The tiles live on the NVMe (C:). This copies to the HDD (D:) — a DIFFERENT
PHYSICAL DISK, so a drive failure cannot take both. It also writes a manifest of
counts + checksums so a later restore can be verified rather than assumed.

    python backup.py            # run the backup
    python backup.py --verify   # check an existing backup against the live corpus
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths

SRC_TILES = paths.TILES_V3
SRC_SCREENER = paths.SCREENER_WEIGHTS
SRC_RIGOR = os.path.dirname(os.path.abspath(__file__))

DEST_ROOT = paths.BACKUP_ROOT_STR

SCALES = ("10x", "20x", "40x", "5x")


def corpus_manifest(root):
    """counts + a content hash of every LABEL (the hand-edited part)."""
    man = {}
    for sc in SCALES:
        for split in ("positives", "negatives"):
            idir = os.path.join(root, f"training_data_{sc}", split, "images")
            ldir = os.path.join(root, f"training_data_{sc}", split, "labels")
            if not os.path.isdir(idir):
                continue
            imgs = sorted(f for f in os.listdir(idir) if f.endswith(".png"))
            h = hashlib.sha256()
            for f in imgs:
                t = os.path.join(ldir, os.path.splitext(f)[0] + ".txt")
                h.update(f.encode())
                if os.path.exists(t):
                    with open(t, "rb") as fh:
                        h.update(fh.read())
            man[f"{sc}/{split}"] = {"n_images": len(imgs),
                                    "label_hash": h.hexdigest()[:16]}
    return man


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=DEST_ROOT)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    live = corpus_manifest(SRC_TILES)

    if args.verify:
        mp = os.path.join(args.dest, "manifest.json")
        if not os.path.exists(mp):
            sys.exit(f"no backup manifest at {mp}")
        with open(mp) as fh:
            saved = json.load(fh)["corpus"]
        ok = True
        for k, v in live.items():
            s = saved.get(k)
            if not s:
                print(f"  MISSING in backup: {k}")
                ok = False
            elif s["label_hash"] != v["label_hash"]:
                print(f"  DIFFERS: {k}  backup={s['n_images']} live={v['n_images']}")
                ok = False
            else:
                print(f"  ok  {k:<22} {v['n_images']:>5} tiles")
        print("\nVERDICT:", "backup matches the live corpus"
              if ok else "*** backup is STALE — re-run backup.py ***")
        return

    os.makedirs(args.dest, exist_ok=True)
    print(f"backing up -> {args.dest}")
    print("(C: NVMe -> D: HDD: a different physical disk, so one failure "
          "cannot destroy both)\n")

    t0 = time.time()

    # 1. the corpus (the hand-reviewed tiles)
    dst_tiles = os.path.join(args.dest, "tiles_v3")
    print("  tiles_v3 (19GB, the hand-reviewed corpus) ...", flush=True)
    if os.path.exists(dst_tiles):
        shutil.rmtree(dst_tiles)
    shutil.copytree(SRC_TILES, dst_tiles)

    # 2. the code + configs that define how it was built
    dst_rigor = os.path.join(args.dest, "rigor")
    print("  rigor/ (code, slides_clean.yaml, splits, manifest) ...", flush=True)
    if os.path.exists(dst_rigor):
        shutil.rmtree(dst_rigor)
    shutil.copytree(SRC_RIGOR, dst_rigor,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # 3. the screener (the negatives depend on it)
    if os.path.exists(SRC_SCREENER):
        os.makedirs(os.path.join(args.dest, "screener"), exist_ok=True)
        shutil.copy2(SRC_SCREENER,
                     os.path.join(args.dest, "screener", "best.pt"))
        print("  screener weights ...", flush=True)

    with open(os.path.join(args.dest, "manifest.json"), "w") as fh:
        json.dump({"created": stamp, "source": SRC_TILES, "corpus": live},
                  fh, indent=2)

    total = sum(v["n_images"] for v in live.values())
    print(f"\nbacked up {total} tiles in {(time.time()-t0)/60:.1f} min")
    for k, v in sorted(live.items()):
        print(f"  {k:<22} {v['n_images']:>5}")
    print(f"\nverify any time with:  python backup.py --verify")


if __name__ == "__main__":
    main()
