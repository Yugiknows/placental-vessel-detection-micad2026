"""
train_deploy_models.py — the PRODUCTION detectors. NOT part of the paper.

TWO DIFFERENT THINGS, DELIBERATELY SEPARATED (user's decision, 2026-07-13):

  1. THE PAPER (run_manifest.py / train_run.py)
     architecture x mosaic x seed, under LOSO, on 10x/20x/40x ONLY.
     5x is EXCLUDED: the brief defines the decomposed arm as three detectors
     (10x large / 20x medium / 40x capillaries), and 5x is unevenly distributed
     (BFD_1 and S.2723_26_CFD_1 have ZERO 5x tiles, so those LOSO folds would have
     no 5x eval data and per-slide AP would be undefined — breaking the paired
     test C4 rests on). Adding it would put holes in a clean 2x2 design.

  2. THIS FILE — the models you actually RUN on new slides.
     All four scales INCLUDING 5x, each trained on EVERY clean slide.

WHY THE PAPER'S MODELS CANNOT BE DEPLOYED
Every LOSO model is deliberately blind to one slide — that is the whole point of
C1. There are 11 of them per cell and none has seen all the data. For inference you
want one model per scale that has seen everything. Different job, different models.

The augmentation here matches the paper's mosaic=0 arm (mosaic/mixup/copy_paste=0,
hsv_s=0.05) so the deployed detector behaves like the configuration the paper
recommends — assuming the experiment confirms mosaic is harmful. If it does not,
revisit this.

    python train_deploy_models.py --scales 5x          # just the 5x model
    python train_deploy_models.py                      # all four
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tiling_config as TC

CORPUS = r"C:\placenta_ssd\tiles_v3"
OUT = r"C:\placenta_ssd\deploy_models"

EPOCHS = 300
PATIENCE = 60
VAL_FRAC = 0.15      # random tile-level split; fine here — this is NOT a reported
                     # metric, it only drives early stopping. C1 governs the PAPER.


def build_yaml(scale, corpus, out_dir):
    import yaml
    imgs = []
    for split in ("positives", "negatives"):
        d = os.path.join(corpus, f"training_data_{scale}", split, "images")
        if os.path.isdir(d):
            imgs += [os.path.join(d, f) for f in sorted(os.listdir(d))
                     if f.endswith(".png")]
    if not imgs:
        return None, 0
    random.Random(0).shuffle(imgs)
    n_val = max(1, int(len(imgs) * VAL_FRAC))
    val, train = imgs[:n_val], imgs[n_val:]

    os.makedirs(out_dir, exist_ok=True)
    tp = os.path.join(out_dir, f"{scale}_train.txt")
    vp = os.path.join(out_dir, f"{scale}_val.txt")
    open(tp, "w").write("\n".join(train) + "\n")
    open(vp, "w").write("\n".join(val) + "\n")

    yp = os.path.join(out_dir, f"{scale}.yaml")
    with open(yp, "w") as fh:
        yaml.safe_dump({"path": corpus, "train": tp, "val": vp,
                        "nc": 1, "names": ["blood_vessel"]}, fh, sort_keys=False)
    return yp, len(imgs)


def main():
    import warnings
    warnings.filterwarnings("ignore")
    from ultralytics import YOLO

    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", nargs="*", default=list(TC.ALL_SCALES),
                    choices=list(TC.ALL_SCALES))
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    args = ap.parse_args()

    print("PRODUCTION detectors — trained on EVERY clean slide.")
    print("NOT the paper's models (those are LOSO, each blind to one slide).\n")

    for sc in args.scales:
        y, n = build_yaml(sc, args.corpus, args.out)
        if not y:
            print(f"{sc}: no tiles — skipped")
            continue
        print(f"\n=== {sc}: {n} tiles ===", flush=True)
        YOLO("yolo11n.pt").train(
            data=y, epochs=args.epochs, imgsz=TC.TILE_SIZE, batch=16,
            device=0, seed=0, patience=PATIENCE, workers=8, deterministic=True,
            # same aug policy as the paper's mosaic=0 arm
            mosaic=0.0, mixup=0.0, copy_paste=0.0,
            hsv_h=0.005, hsv_s=0.05, hsv_v=0.10,
            project=args.out, name=f"deploy_{sc}", exist_ok=True,
            verbose=False, plots=False,
        )
        print(f"  -> {args.out}\\deploy_{sc}\\weights\\best.pt")

    print("\nPoint run_inference.py's SCALES at these weights.")


if __name__ == "__main__":
    main()
