"""
regen_negatives.py — rebuild ONLY the negative tiles: 1:1 with positives, and
SCREENED so they actually contain no vessel.

TWO PROBLEMS THIS SOLVES

1) The user reviewed every POSITIVE tile in labelImg (566/756 of the 10x labels
   were edited; some tiles deleted). Re-running the main tiler would regenerate
   positives from the .ndpa and destroy that work. This script never opens the
   positives directory for writing — it only reads it, to count how many
   negatives each slide needs and to avoid regions already taken.

2) The .ndpa annotations are NOT exhaustive. The pathologist annotated a SUBSET
   of vessels, so "no annotation overlaps this tile" != "no vessel in this tile".
   Measured: 11% / 15% / 5% / 9% (10x/20x/40x/5x) of the previous negatives
   contained a visible vessel. An unlabelled vessel in a negative tile teaches
   the detector that a vessel IS background — the most damaging label noise
   possible for a recall-sensitive claim.

   So each candidate is screened with the TRUSTED pre-contamination model
   (dated before the first NDPA overwrite, so it cannot carry fabricated boxes).
   Any candidate where it detects a vessel at >= TC.NEG_SCREEN_CONF is DISCARDED.
   No model output ever becomes a label — this is rejection, not annotation.

Pipeline per (slide, scale):
    tissue mask -> candidate origins -> reject overlap w/ ANY annotation
    -> reject overlap w/ any positive tile -> GPU screen -> keep first N
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import tiling_config as TC

CORPUS = r"C:\placenta_ssd\tiles_v3"
SLIDES_ROOT = r"C:\placenta_ssd\slides"
MODEL = (r"D:\windows_gpu_migration\Yolo11_training-yolo11_train_seg_classify"
         r"\blood_vessel_best_BACKUP.pt")
BATCH = 16


def positives_on_disk(corpus, scale, sid):
    d = os.path.join(corpus, f"training_data_{scale}", "positives", "images")
    if not os.path.isdir(d):
        return []
    out, pre = [], f"{sid}_{scale}_"
    for f in os.listdir(d):
        if not f.startswith(pre) or not f.endswith(".png"):
            continue
        try:
            x, y = os.path.splitext(f)[0][len(pre):].split("_")[:2]
            out.append((int(x), int(y)))
        except ValueError:
            pass
    return out


def screen_batch(nets, pil_imgs):
    """True for each image that is CLEAN (no model saw a vessel).

    UNION of every model, with TTA. A candidate survives only if EVERY detector,
    under augmentation, sees nothing. One model was not enough — the user could
    still see vessels in tiles the single pre-contamination model passed.
    """
    verdict = [True] * len(pil_imgs)
    for net in nets:
        preds = net.predict(pil_imgs, conf=TC.NEG_SCREEN_CONF, iou=0.5,
                            augment=TC.NEG_SCREEN_TTA, verbose=False, device=0)
        for i, r in enumerate(preds):
            if any(int(b.cls) == 0 for b in r.boxes):
                verdict[i] = False
    return verdict


def candidates(slide, bboxes, occupied, tile_l0, level, W0, H0, rng):
    """Tissue-guided origins that touch NO annotation and NO positive tile.

    Sampling origins uniformly over the slide fails badly — a WSI is mostly blank
    glass, so nearly every draw is rejected and the attempt budget runs out
    (we were getting 275/1244 at 40x). Find the tissue once, from a thumbnail.
    """
    tl = slide.level_count - 1
    while tl > 0 and slide.level_dimensions[tl][0] < 512:
        tl -= 1
    tds = slide.level_downsamples[tl]
    thumb = np.array(slide.read_region((0, 0), tl,
                                       slide.level_dimensions[tl]).convert("RGB"))
    tissue = thumb.mean(axis=2) < TC.WHITE_THRESH

    # Vessels branch beyond the box a pathologist drew, so a tile that merely
    # fails to OVERLAP an annotation can still hold that vessel's continuation.
    # Inflate every annotation by a margin before testing.
    m = tile_l0 * TC.NEG_ANNOT_MARGIN_FRAC
    grown = [(ax1 - m, ay1 - m, ax2 + m, ay2 + m) for (ax1, ay1, ax2, ay2) in bboxes]

    step = tile_l0 / 2.0
    out = []
    for iy in range(int(max(1, (H0 - tile_l0) // step))):
        for ix in range(int(max(1, (W0 - tile_l0) // step))):
            tx1, ty1 = int(ix * step), int(iy * step)
            cx, cy = int((tx1 + tile_l0 / 2) / tds), int((ty1 + tile_l0 / 2) / tds)
            if not (0 <= cy < tissue.shape[0] and 0 <= cx < tissue.shape[1]):
                continue
            if not tissue[cy, cx]:
                continue
            tx2, ty2 = tx1 + tile_l0, ty1 + tile_l0
            if any(not (ax2 <= tx1 or ax1 >= tx2 or ay2 <= ty1 or ay1 >= ty2)
                   for (ax1, ay1, ax2, ay2) in grown):
                continue
            if any(not (ox2 <= tx1 or ox1 >= tx2 or oy2 <= ty1 or oy1 >= ty2)
                   for (ox1, oy1, ox2, oy2) in occupied):
                continue
            out.append((tx1, ty1))
    rng.shuffle(out)
    return out


def main():
    os.environ.setdefault("PLACENTA_SLIDES_ROOT", SLIDES_ROOT)
    import warnings
    warnings.filterwarnings("ignore")
    import openslide
    from ultralytics import YOLO

    from annotation_scale_report import discover_clean_sources
    from prepare_training_tiles import parse_ndpa_bboxes
    from slide_registry import load_clean_slides

    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--scales", nargs="*", default=list(TC.ALL_SCALES))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    # C2 + trusted-model gate: refuse a model that could carry fabricated boxes
    from preannotate_labelimg import assert_trusted_model
    assert_trusted_model(args.model)

    slides = load_clean_slides()
    src = discover_clean_sources()

    # UNION of detectors. A vessel must fool ALL of them to reach the corpus.
    SCREENER = r"C:\placenta_ssd\screener\run\weights\best.pt"
    paths = [args.model]
    if os.path.exists(SCREENER):
        paths.append(SCREENER)
    else:
        sys.exit(f"screener not trained yet: {SCREENER}\n"
                 "Train it first — the pre-contamination model alone misses "
                 "~1 in 10 vessels and is not sufficient on its own.")
    nets = [YOLO(p) for p in paths]
    print(f"screening with {len(nets)} models (union, TTA={TC.NEG_SCREEN_TTA}):")
    for p in paths:
        print(f"  - {os.path.basename(p)}")

    # ── SANITY GATE: prove the screener can actually SEE vessels ──────────────
    # A screener that silently detects nothing looks identical to a screener that
    # finds nothing to reject — and that is exactly what happened: passing numpy
    # RGB (ultralytics reads numpy as BGR) made the model return 0 detections on
    # tiles full of vessels, so every candidate "passed". Refuse to run unless the
    # model fires on known-positive tiles fed the same way negatives will be.
    import glob as _glob
    from PIL import Image as _Image
    probe = []
    for _sc in ("10x", "20x", "40x"):
        _fs = _glob.glob(os.path.join(
            args.corpus, f"training_data_{_sc}", "positives", "images", "*.png"))
        random.Random(7).shuffle(_fs)      # random, not the first-N alphabetically
        probe += _fs[:30]                  # (which all came from one slide)
    if probe:
        pil = [_Image.open(p).convert("RGB") for p in probe]
        caught = 0
        for i in range(0, len(pil), BATCH):
            # screen_batch returns True = "looks clean"; on a POSITIVE tile that
            # is a MISS. Recall = fraction we correctly flag as dirty.
            caught += sum(1 for ok in screen_batch(nets, pil[i:i + BATCH]) if not ok)
        rate = caught / len(probe)
        print(f"screener sanity: the union flags {caught}/{len(probe)} "
              f"known-POSITIVE tiles as containing a vessel ({rate:.0%} recall)")
        if rate < 0.95:
            sys.exit(
                f"REFUSING TO RUN: the screening union catches only {rate:.0%} of "
                f"known-positive tiles at conf={TC.NEG_SCREEN_CONF}. Anything it "
                "misses becomes a negative tile containing a visible vessel — the "
                "exact defect we are fixing. Need >=95%. Train a stronger screener "
                "or lower NEG_SCREEN_CONF.\n"
                "(Also check the image format: numpy is read as BGR, PIL as RGB.)")
    print()

    print(f"negatives: 1:1 with surviving positives, screened at "
          f"conf>={TC.NEG_SCREEN_CONF} with the TRUSTED model")
    print("positives are NOT touched — the labelImg review is preserved.\n")
    print(f"{'scale':<6}{'slide':<24}{'pos':>5}{'neg':>6}{'rejected(vessel)':>18}")
    print("-" * 60)

    t0 = time.time()
    tot_p = tot_n = tot_rej = 0
    for sc in args.scales:
        g = TC.SCALE_GATES[sc]
        for sid in slides:
            if sid not in src or not src[sid][1]:
                continue
            ndpa, ndpi, _ = src[sid]
            pos = positives_on_disk(args.corpus, sc, sid)
            want = min(TC.NEG_CAP, int(len(pos) * TC.NEG_RATIO))

            ni = os.path.join(args.corpus, f"training_data_{sc}", "negatives", "images")
            nl = os.path.join(args.corpus, f"training_data_{sc}", "negatives", "labels")
            os.makedirs(ni, exist_ok=True)
            os.makedirs(nl, exist_ok=True)

            pre = f"{sid}_{sc}_"
            for d, ext in ((ni, ".png"), (nl, ".txt")):
                for f in os.listdir(d):
                    if f.startswith(pre) and f.endswith(ext):
                        os.remove(os.path.join(d, f))
            if want == 0:
                continue

            slide = openslide.OpenSlide(ndpi)
            bboxes = parse_ndpa_bboxes(ndpa, slide)
            level = slide.get_best_level_for_downsample(g["downsample"])
            ads = slide.level_downsamples[level]
            W0, H0 = slide.dimensions
            tile_l0 = TC.TILE_SIZE * ads
            occupied = [(x, y, x + tile_l0, y + tile_l0) for x, y in pos]
            rng = random.Random(f"{sid}|{sc}|{args.seed}|neg")

            cands = candidates(slide, bboxes, occupied, tile_l0, level, W0, H0, rng)

            kept = rej = 0
            i = 0
            while kept < want and i < len(cands):
                chunk = cands[i:i + BATCH]
                i += BATCH
                imgs, origins = [], []
                for (tx1, ty1) in chunk:
                    im = slide.read_region((tx1, ty1), level,
                                           (TC.TILE_SIZE, TC.TILE_SIZE)).convert("RGB")
                    if np.array(im).mean() > TC.WHITE_THRESH:   # blank glass
                        continue
                    # Pass the PIL image, NOT np.array(im).
                    # Ultralytics interprets a raw numpy array as BGR (OpenCV
                    # convention). Handing it an RGB array silently swaps the
                    # colour channels and the model goes effectively blind — on
                    # tiles that definitely contain vessels it returned 0
                    # detections vs 14 for the same tiles as PIL/paths. That made
                    # the screener a no-op and let vessel-bearing tiles through.
                    imgs.append(im)
                    origins.append((tx1, ty1, im))
                if not imgs:
                    continue

                # SCREEN: discard unless EVERY model (with TTA) sees nothing
                clean = screen_batch(nets, imgs)
                for (tx1, ty1, im), ok in zip(origins, clean):
                    if kept >= want:
                        break
                    if not ok:
                        rej += 1
                        continue
                    name = f"{sid}_{sc}_{int(tx1):07d}_{int(ty1):07d}"
                    im.save(os.path.join(ni, name + ".png"))
                    open(os.path.join(nl, name + ".txt"), "w").close()
                    kept += 1
            slide.close()

            flag = "" if kept == want else f"  <-- {kept}/{want}"
            print(f"{sc:<6}{sid:<24}{len(pos):>5}{kept:>6}{rej:>18}{flag}")
            tot_p += len(pos)
            tot_n += kept
            tot_rej += rej

    print("-" * 60)
    print(f"{'TOTAL':<30}{tot_p:>5}{tot_n:>6}{tot_rej:>18}")
    print(f"\n{tot_rej} candidates discarded because the trusted model saw a "
          f"vessel in them.\nfinished in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
