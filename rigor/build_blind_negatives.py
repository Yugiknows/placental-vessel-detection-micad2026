"""
build_blind_negatives.py — reconstruct the UNSCREENED negatives (for ablation C).

These are the negatives you get from the obvious rule:
    "a tile with tissue that no annotation overlaps is background"

That rule is WRONG here, because the pathologist's annotations are not exhaustive
— they marked a SUBSET of vessels. Measured earlier: ~35% of these tiles contain
real, visible, unlabelled vessels. Training on them teaches the detector that a
visible vessel IS background, which suppresses recall.

Ablation C trains on exactly these, holding the positives constant (vessel-centred),
so the recall damage is attributable to the negatives alone.

NO model screening, NO annotation margin — deliberately. This reproduces the bug.
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import tiling_config as TC
from ablations import BLIND, STUDY_SCALES

CORPUS = r"C:\placenta_ssd\tiles_v3"
SLIDES_ROOT = r"C:\placenta_ssd\slides"


def positives_on_disk(scale, sid):
    d = os.path.join(CORPUS, f"training_data_{scale}", "positives", "images")
    if not os.path.isdir(d):
        return []
    out, pre = [], f"{sid}_{scale}_"
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

    from annotation_scale_report import discover_clean_sources
    from prepare_training_tiles import parse_ndpa_bboxes
    from slide_registry import load_clean_slides

    slides = load_clean_slides()
    src = discover_clean_sources()

    print("Building BLIND (unscreened) negatives — reproducing the bug.")
    print("Rule: tissue + no annotation overlap = 'background'.")
    print("This is WRONG: annotations are non-exhaustive, so ~35% will hold "
          "real vessels.\n")
    print(f"{'scale':<6}{'slide':<24}{'neg':>6}")
    print("-" * 40)

    t0 = time.time()
    total = 0
    for sc in STUDY_SCALES:
        g = TC.SCALE_GATES[sc]
        for sid in slides:
            if sid not in src or not src[sid][1]:
                continue
            ndpa, ndpi, _ = src[sid]
            pos = positives_on_disk(sc, sid)
            want = len(pos)                      # 1:1, same as the screened set
            if want == 0:
                continue

            ni = os.path.join(BLIND, f"training_data_{sc}", "negatives", "images")
            nl = os.path.join(BLIND, f"training_data_{sc}", "negatives", "labels")
            os.makedirs(ni, exist_ok=True)
            os.makedirs(nl, exist_ok=True)

            slide = openslide.OpenSlide(ndpi)
            bboxes = parse_ndpa_bboxes(ndpa, slide)
            level = slide.get_best_level_for_downsample(g["downsample"])
            ads = slide.level_downsamples[level]
            W0, H0 = slide.dimensions
            tile_l0 = TC.TILE_SIZE * ads
            occupied = [(x, y, x + tile_l0, y + tile_l0) for x, y in pos]

            # tissue mask (same as the screened path — the ONLY difference is that
            # no detector screening and no annotation margin is applied)
            tl = slide.level_count - 1
            while tl > 0 and slide.level_dimensions[tl][0] < 512:
                tl -= 1
            tds = slide.level_downsamples[tl]
            thumb = np.array(slide.read_region((0, 0), tl,
                             slide.level_dimensions[tl]).convert("RGB"))
            tissue = thumb.mean(axis=2) < TC.WHITE_THRESH

            step = tile_l0 / 2.0
            cands = []
            for iy in range(int(max(1, (H0 - tile_l0) // step))):
                for ix in range(int(max(1, (W0 - tile_l0) // step))):
                    tx1, ty1 = int(ix * step), int(iy * step)
                    cx, cy = int((tx1 + tile_l0/2)/tds), int((ty1 + tile_l0/2)/tds)
                    if not (0 <= cy < tissue.shape[0] and 0 <= cx < tissue.shape[1]):
                        continue
                    if not tissue[cy, cx]:
                        continue
                    tx2, ty2 = tx1 + tile_l0, ty1 + tile_l0
                    # NO MARGIN — bare overlap test, exactly the flawed rule
                    if any(not (a2 <= tx1 or a1 >= tx2 or b2 <= ty1 or b1 >= ty2)
                           for (a1, b1, a2, b2) in bboxes):
                        continue
                    if any(not (o3 <= tx1 or o1 >= tx2 or o4 <= ty1 or o2 >= ty2)
                           for (o1, o2, o3, o4) in occupied):
                        continue
                    cands.append((tx1, ty1))

            random.Random(f"{sid}|{sc}|0|blind").shuffle(cands)
            got = 0
            for (tx1, ty1) in cands:
                if got >= want:
                    break
                im = slide.read_region((tx1, ty1), level,
                                       (TC.TILE_SIZE, TC.TILE_SIZE)).convert("RGB")
                if np.array(im).mean() > TC.WHITE_THRESH:
                    continue
                # NO DETECTOR SCREENING — this is the whole point
                name = f"{sid}_{sc}_{int(tx1):07d}_{int(ty1):07d}"
                im.save(os.path.join(ni, name + ".png"))
                open(os.path.join(nl, name + ".txt"), "w").close()
                got += 1
            slide.close()
            print(f"{sc:<6}{sid:<24}{got:>6}", flush=True)
            total += got

    print("-" * 40)
    print(f"TOTAL blind negatives: {total}  ({(time.time()-t0)/60:.1f} min)")
    print(f"-> {BLIND}")


if __name__ == "__main__":
    main()
