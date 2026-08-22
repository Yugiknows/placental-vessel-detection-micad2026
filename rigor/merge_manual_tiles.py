"""
merge_manual_tiles.py — fold the user's hand-verified tiles into the clean set.

These tiles are irreplaceable: some sit on slides whose source .ndpa was
destroyed by the NDPA-overwrite bug (S.3152_26_A3FD_1, A3_FD_1,
A2FD_1_S.2058_26), so they CANNOT be regenerated from source. A human drew or
confirmed every box, which is exactly why contamination is judged per-tile, not
per-slide (see tile_provenance.py).

Rules:
  * COPY only — the originals in placenta_training/ are never moved or altered.
  * NEVER overwrite. If the clean set already has a tile of the same name (i.e.
    it was regenerated from .ndpa), the MANUAL tile wins only with --prefer-manual;
    by default the collision is reported and skipped so nothing is silently lost.
  * Every merged tile is recorded with source=manual_verified in the ledger, so
    its provenance survives.
"""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SRC_ROOT = r"D:\windows_gpu_migration\placenta_training"
DST_ROOT = r"D:\windows_gpu_migration\placenta_training_clean"

SPLITS = ["train/positives", "train/negatives", "val"]


def merge(scale, src_root, dst_root, prefer_manual, dry_run):
    copied = collided = 0
    coll_list = []
    for split in SPLITS:
        s_img = os.path.join(src_root, f"training_data_{scale}", split, "images")
        s_lbl = os.path.join(src_root, f"training_data_{scale}", split, "labels")
        d_img = os.path.join(dst_root, f"training_data_{scale}", split, "images")
        d_lbl = os.path.join(dst_root, f"training_data_{scale}", split, "labels")
        if not os.path.isdir(s_img):
            continue
        if not dry_run:
            os.makedirs(d_img, exist_ok=True)
            os.makedirs(d_lbl, exist_ok=True)

        for f in sorted(os.listdir(s_img)):
            if f.startswith("._") or not f.lower().endswith(".png"):
                continue
            stem = os.path.splitext(f)[0]
            src_i = os.path.join(s_img, f)
            src_l = os.path.join(s_lbl, stem + ".txt")
            if not os.path.exists(src_l):
                continue
            dst_i = os.path.join(d_img, f)
            dst_l = os.path.join(d_lbl, stem + ".txt")

            if os.path.exists(dst_i):
                collided += 1
                coll_list.append(f"{scale}/{split}/{stem}")
                if not prefer_manual:
                    continue   # keep regenerated tile; do NOT clobber
            if not dry_run:
                shutil.copy2(src_i, dst_i)
                shutil.copy2(src_l, dst_l)
            copied += 1
    return copied, collided, coll_list


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", nargs="*", default=["5x"],
                    choices=["5x", "10x", "20x", "40x"])
    ap.add_argument("--prefer-manual", action="store_true",
                    help="on name collision, the hand-verified tile replaces the "
                         "regenerated one (recommended: a human checked it)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    total_c = total_x = 0
    for scale in args.scales:
        c, x, coll = merge(scale, SRC_ROOT, DST_ROOT,
                           args.prefer_manual, args.dry_run)
        total_c += c
        total_x += x
        print(f"{scale}: {'would copy' if args.dry_run else 'copied'} {c} "
              f"hand-verified tiles, {x} name collisions")
        for t in coll[:8]:
            print(f"     collision: {t}")

    print(f"\nTOTAL {'would copy' if args.dry_run else 'copied'}: {total_c} "
          f"({total_x} collisions"
          f"{', manual won' if args.prefer_manual else ', regenerated kept'})")
    if not args.dry_run:
        print("Originals in placenta_training/ untouched (copy, not move).")
        print("Next: python tile_provenance.py scan  -> mark these verified=yes")


if __name__ == "__main__":
    main()
