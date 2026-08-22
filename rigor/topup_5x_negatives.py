"""
topup_5x_negatives.py — generate MORE 5x negatives for manual verification.

WHY 5x IS DIFFERENT
A 5x tile spans 16,384 level-0 px. Placental villous tissue is packed with fetal
capillaries, so a field that large almost always contains a vessel somewhere —
we rejected 43,486 candidates corpus-wide to keep 2,269, and at 5x only TWO
tiles survived a hard reject threshold. "Placental tissue with no vessel in it"
is nearly a contradiction at low magnification.

SO: RANK, DON'T THRESHOLD.
Instead of discarding anything the detectors flag, score every candidate by how
vessel-like it is (max detection confidence across the model union, with TTA) and
keep the LEAST vessel-like ones. That surfaces the best tiles that actually exist
rather than insisting on a purity the tissue cannot supply. The user verifies the
~55 survivors by hand — which is the only trustworthy check anyway, since the
model is what missed vessels in the first place.

Also relaxed FOR 5x ONLY:
  * annotation margin 0.25 -> 0.05. At 5x the 25% margin is 4,096 l0px of
    exclusion around every annotation, which alone erases most of the slide.
  * candidate stride 1/2 tile -> 1/4 tile, for a denser search.

HARD SAFETY GUARD
This writes ONLY to training_data_5x/negatives. It asserts that on every path it
touches, and it never opens 10x/20x/40x — nor 5x POSITIVES — for writing. The
user has hand-reviewed those and they must not be disturbed.

    python topup_5x_negatives.py --target 60
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths
import numpy as np

import tiling_config as TC

CORPUS = paths.TILES_V3
SLIDES_ROOT = paths.SLIDES
TRUSTED = paths.TRUSTED_MODEL
SCREENER = paths.SCREENER_WEIGHTS

SCALE = "5x"
MARGIN_FRAC = 0.05      # relaxed from 0.25 (at 5x that was 4096 l0px)
STRIDE_FRAC = 0.25      # denser than the 0.5 used elsewhere
BATCH = 8


def assert_only_5x_negatives(path):
    """HARD GUARD: refuse to write anywhere except 5x negatives."""
    p = os.path.abspath(path).replace("\\", "/").lower()
    if "/training_data_5x/negatives/" not in p:
        raise RuntimeError(
            f"REFUSED to write outside 5x negatives: {path}\n"
            "The 10x/20x/40x tiles and the 5x positives are hand-reviewed and "
            "must not be touched.")
    for forbidden in ("training_data_10x", "training_data_20x",
                      "training_data_40x", "/positives/"):
        if forbidden in p:
            raise RuntimeError(f"REFUSED: path touches protected data: {path}")


def existing_5x_negatives(corpus):
    d = os.path.join(corpus, f"training_data_{SCALE}", "negatives", "images")
    if not os.path.isdir(d):
        return set()
    return {os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith(".png")}


def positives_5x(corpus, sid):
    d = os.path.join(corpus, f"training_data_{SCALE}", "positives", "images")
    if not os.path.isdir(d):
        return []
    out, pre = [], f"{sid}_{SCALE}_"
    for f in os.listdir(d):
        if f.startswith(pre) and f.endswith(".png"):
            try:
                x, y = os.path.splitext(f)[0][len(pre):].split("_")[:2]
                out.append((int(x), int(y)))
            except ValueError:
                pass
    return out


def main():
    os.environ.setdefault("PLACENTA_SLIDES_ROOT", SLIDES_ROOT)
    import warnings
    warnings.filterwarnings("ignore")
    import openslide
    from PIL import Image
    from ultralytics import YOLO

    from annotation_scale_report import discover_clean_sources
    from prepare_training_tiles import parse_ndpa_bboxes
    from slide_registry import load_clean_slides

    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--target", type=int, default=60,
                    help="how many 5x negatives to end up with (for hand review)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    slides = load_clean_slides()
    src = discover_clean_sources()
    nets = [YOLO(TRUSTED), YOLO(SCREENER)]

    have = existing_5x_negatives(args.corpus)
    print(f"5x negatives already present: {len(have)} (kept, not deleted)")
    need = max(0, args.target - len(have))
    print(f"target {args.target} -> generating {need} more\n")
    if need == 0:
        return

    g = TC.SCALE_GATES[SCALE]
    ni = os.path.join(args.corpus, f"training_data_{SCALE}", "negatives", "images")
    nl = os.path.join(args.corpus, f"training_data_{SCALE}", "negatives", "labels")
    assert_only_5x_negatives(ni)
    assert_only_5x_negatives(nl)
    os.makedirs(ni, exist_ok=True)
    os.makedirs(nl, exist_ok=True)

    scored = []          # (max_vessel_conf, slide, x, y, PIL) — lower is better
    t0 = time.time()

    for sid in slides:
        if sid not in src or not src[sid][1]:
            continue
        ndpa, ndpi, _ = src[sid]
        slide = openslide.OpenSlide(ndpi)
        bboxes = parse_ndpa_bboxes(ndpa, slide)
        level = slide.get_best_level_for_downsample(g["downsample"])
        ads = slide.level_downsamples[level]
        W0, H0 = slide.dimensions
        tile_l0 = TC.TILE_SIZE * ads

        occupied = [(x, y, x + tile_l0, y + tile_l0)
                    for x, y in positives_5x(args.corpus, sid)]
        m = tile_l0 * MARGIN_FRAC
        grown = [(a - m, b - m, c + m, d + m) for (a, b, c, d) in bboxes]

        # tissue mask
        tl = slide.level_count - 1
        while tl > 0 and slide.level_dimensions[tl][0] < 512:
            tl -= 1
        tds = slide.level_downsamples[tl]
        thumb = np.array(slide.read_region((0, 0), tl,
                         slide.level_dimensions[tl]).convert("RGB"))
        tissue = thumb.mean(axis=2) < TC.WHITE_THRESH

        step = tile_l0 * STRIDE_FRAC
        cands = []
        for iy in range(int(max(1, (H0 - tile_l0) // step))):
            for ix in range(int(max(1, (W0 - tile_l0) // step))):
                tx1, ty1 = int(ix * step), int(iy * step)
                cx, cy = int((tx1 + tile_l0 / 2) / tds), int((ty1 + tile_l0 / 2) / tds)
                if not (0 <= cy < tissue.shape[0] and 0 <= cx < tissue.shape[1]):
                    continue
                if not tissue[cy, cx]:
                    continue
                name = f"{sid}_{SCALE}_{int(tx1):07d}_{int(ty1):07d}"
                if name in have:
                    continue
                tx2, ty2 = tx1 + tile_l0, ty1 + tile_l0
                if any(not (a2 <= tx1 or a1 >= tx2 or b2 <= ty1 or b1 >= ty2)
                       for (a1, b1, a2, b2) in grown):
                    continue
                if any(not (o3 <= tx1 or o1 >= tx2 or o4 <= ty1 or o2 >= ty2)
                       for (o1, o2, o3, o4) in occupied):
                    continue
                cands.append((tx1, ty1))

        random.Random(f"{sid}|{args.seed}").shuffle(cands)
        cands = cands[:120]           # cap per slide; scoring is the expensive bit

        for i in range(0, len(cands), BATCH):
            chunk = cands[i:i + BATCH]
            imgs, keys = [], []
            for (tx1, ty1) in chunk:
                im = slide.read_region((tx1, ty1), level,
                                       (TC.TILE_SIZE, TC.TILE_SIZE)).convert("RGB")
                if np.array(im).mean() > TC.WHITE_THRESH:
                    continue
                imgs.append(im)
                keys.append((tx1, ty1))
            if not imgs:
                continue
            # RANK: worst-case vessel confidence across BOTH models, with TTA
            worst = [0.0] * len(imgs)
            for net in nets:
                for j, r in enumerate(net.predict(imgs, conf=0.01, iou=0.5,
                                                  augment=True, verbose=False,
                                                  device=0)):
                    cs = [float(b.conf) for b in r.boxes if int(b.cls) == 0]
                    if cs:
                        worst[j] = max(worst[j], max(cs))
            for (tx1, ty1), im, w in zip(keys, imgs, worst):
                scored.append((w, sid, tx1, ty1, im))
        slide.close()
        print(f"  {sid:<24} scored {len([s for s in scored if s[1]==sid]):>4} candidates",
              flush=True)

    scored.sort(key=lambda s: s[0])          # least vessel-like first
    take = scored[:need]

    print(f"\nkeeping the {len(take)} LEAST vessel-like of {len(scored)} candidates")
    if take:
        print(f"  vessel-confidence of kept tiles: "
              f"min={take[0][0]:.3f}  max={take[-1][0]:.3f}")
        clean = sum(1 for t in take if t[0] == 0.0)
        print(f"  {clean}/{len(take)} have ZERO detections from either model")

    for w, sid, tx1, ty1, im in take:
        name = f"{sid}_{SCALE}_{int(tx1):07d}_{int(ty1):07d}"
        ip = os.path.join(ni, name + ".png")
        lp = os.path.join(nl, name + ".txt")
        assert_only_5x_negatives(ip)
        assert_only_5x_negatives(lp)
        im.save(ip)
        open(lp, "w").close()

    total = len(existing_5x_negatives(args.corpus))
    print(f"\n5x negatives now: {total}   (in {(time.time()-t0)/60:.1f} min)")
    print("VERIFY THESE BY HAND — at 5x the tissue is so vascular that these are "
          "the best available, not guaranteed clean.")


if __name__ == "__main__":
    main()
