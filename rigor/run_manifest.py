"""
run_manifest.py — the source of truth for every training run (4.1).

Core grid: 2 architectures x 2 mosaic x 3 seeds, each under LOSO.
Because per_mag_3x is THREE models (10x/20x/40x) per config, one "config" is not
one training job. Actual job count:

    single_allmag : 2 mosaic x 3 seeds x N folds x 1 model
    per_mag_3x    : 2 mosaic x 3 seeds x N folds x 3 models

Augmentation policy (§3), applied identically in every cell except the one
factor under test:
    mosaic=0.0 -> mosaic=0, mixup=0, copy_paste=0
    mosaic=1.0 -> mosaic=1, mixup/copy_paste at ultralytics defaults (both 0.0)
    hsv_s = 0.05 everywhere in the core grid (colour held CONSTANT)
    --color-arm adds ONLY per_mag_3x x mosaic=0 x hsv_s=0.70 x 3 seeds. Nothing else.

run_id is deterministic, so the runner is resumable: a run whose metrics exist
AND whose tiling_hash matches is skipped (C3).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
import tiling_config as TC

RIGOR = os.path.dirname(os.path.abspath(__file__))
SPLITS = os.path.join(RIGOR, "splits_v3")
RUNS_ROOT = paths.RUNS_V3
MANIFEST = os.path.join(RIGOR, "run_manifest.json")

ARCHS = ("single_allmag", "per_mag_3x")
MOSAICS = (0.0, 1.0)
SEEDS = (0, 1, 2)
HSV_S_CORE = 0.05
HSV_S_COLOR = 0.70

# identical across every cell (§3) — only arch/mosaic/seed (+hsv in colour arm) vary
#
# EPOCHS — do NOT lower this from a mosaic=0 pilot alone.
# Mosaic is a harder, more heavily-regularised training task, so mosaic=1.0 runs
# typically converge LATER than mosaic=0.0 runs. An epoch cap chosen from the
# mosaic=0 arm would truncate the mosaic=1 arm before it converges, making mosaic
# look worse than it is — i.e. it would MANUFACTURE the paper's own hypothesis
# ("mosaic harms the decomposed detector") as a training artefact. That is a
# reject-trigger, not an efficiency trade.
# The cap must be set from whichever arm converges SLOWEST, and every run must be
# shown to have plateaued before its cap. See pilot.py.
#
# BATCH — measured: at imgsz=1024 the RTX 4060 sits at 96% GPU util with only
# 3.9/8.2 GB VRAM used at batch=8. batch=16 fills the card. It buys little speed
# (the GPU is compute-bound, not starved) but costs nothing.
FIXED = {
    "model": "yolo11n.pt",
    "imgsz": 1024,
    "epochs": 300,          # provisional — the pilot sets the real cap
    "patience": 60,
    "batch": 16,
    "optimizer": "auto",
    "hsv_h": 0.005,
    "hsv_v": 0.10,
    "device": "cuda",
}


def aug_for(mosaic, hsv_s):
    """Resolved augmentation. mixup/copy_paste are 0.0 at ultralytics defaults."""
    return {
        "mosaic": mosaic,
        "mixup": 0.0,
        "copy_paste": 0.0,
        "hsv_h": FIXED["hsv_h"],
        "hsv_s": hsv_s,
        "hsv_v": FIXED["hsv_v"],
    }


def run_id(arch, scale, fold, mosaic, hsv_s, seed):
    return (f"{arch}__{scale}__fold{fold}__mosaic{mosaic:g}"
            f"__hsv{hsv_s:g}__seed{seed}")


def build(folds, color_arm=False):
    runs = []

    def add(arch, scale, fold, mosaic, hsv_s, seed, cell):
        rid = run_id(arch, scale, fold, mosaic, hsv_s, seed)
        yaml_name = "single_allmag" if arch == "single_allmag" else f"per_mag_{scale}"
        runs.append({
            "run_id": rid,
            "cell": cell,                       # the experimental cell it belongs to
            "arch": arch,
            "scale": scale,
            "fold": fold,
            "mosaic": mosaic,
            "hsv_s": hsv_s,
            "seed": seed,
            "data_yaml": os.path.join(SPLITS, f"fold{fold}", f"{yaml_name}.yaml"),
            "out_dir": os.path.join(RUNS_ROOT, rid),
            "aug": aug_for(mosaic, hsv_s),
            "fixed": FIXED,
        })

    for mosaic in MOSAICS:
        for seed in SEEDS:
            for fold in folds:
                cell = f"single_allmag|mosaic{mosaic:g}|hsv{HSV_S_CORE:g}|seed{seed}"
                add("single_allmag", "all", fold, mosaic, HSV_S_CORE, seed, cell)
                for sc in TC.CORE_SCALES:
                    cell3 = f"per_mag_3x|mosaic{mosaic:g}|hsv{HSV_S_CORE:g}|seed{seed}"
                    add("per_mag_3x", sc, fold, mosaic, HSV_S_CORE, seed, cell3)

    if color_arm:
        # ONLY per_mag_3x x mosaic=0 x hsv 0.70 x 3 seeds (§3). Not a 24-run grid.
        for seed in SEEDS:
            for fold in folds:
                for sc in TC.CORE_SCALES:
                    cell = f"per_mag_3x|mosaic0|hsv{HSV_S_COLOR:g}|seed{seed}"
                    add("per_mag_3x", sc, fold, 0.0, HSV_S_COLOR, seed, cell)

    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--color-arm", action="store_true",
                    help="add the +3-cell colour arm (default OFF)")
    ap.add_argument("--out", default=MANIFEST)
    args = ap.parse_args()

    fp = os.path.join(SPLITS, "loso_folds.json")
    if not os.path.exists(fp):
        sys.exit("no LOSO splits — run `python loso_v3.py --write` first (C1).")
    with open(fp) as fh:
        splits = json.load(fh)
    folds = [f["fold"] for f in splits["folds"]]

    from tiling_fingerprint import fingerprint
    fpr = fingerprint()

    runs = build(folds, args.color_arm)
    doc = {
        "tiling_hash": fpr["tiling_hash"],
        "tiling": TC.as_dict(),
        "n_folds": len(folds),
        "n_runs": len(runs),
        "color_arm": args.color_arm,
        "runs": runs,
    }
    with open(args.out, "w") as fh:
        json.dump(doc, fh, indent=2)

    n_single = sum(1 for r in runs if r["arch"] == "single_allmag")
    n_per = sum(1 for r in runs if r["arch"] == "per_mag_3x")
    cells = len({r["cell"] for r in runs})
    print(f"tiling_hash : {fpr['tiling_hash']}  (method={TC.METHOD})")
    print(f"folds       : {len(folds)}  (LOSO)")
    print(f"cells       : {cells}   <- experimental cells (>=3 seeds each: C5)")
    print(f"runs        : {len(runs)} model trainings")
    print(f"  single_allmag : {n_single}")
    print(f"  per_mag_3x    : {n_per}  (3 scale models per config)")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
