"""
run_ablations.py — execute the ablation suite + epoch-cap pilot, and log the
evidence the handoff contract requires (§3.2).

Every run, before it trains:
  * asserts C3 (corpus hash == 7b191fa9e02e) — aborts otherwise
  * asserts C1 on the ACTUAL image lists the framework will read — aborts otherwise
Every run, after it trains, writes:
  * manifest.json     config, seed, tiling hash, exact train/val SLIDE lists,
                      git commit, dataset yaml, ultralytics version, command line
  * results.csv       raw Ultralytics per-epoch metrics, unedited
  * args.yaml         the config actually used
  * metrics_final.json  the four headline metrics on the held-out slide + the
                      epoch each was measured at

Conditions — all single_allmag, mosaic=0, seed=0, 10x/20x/40x, 5x EXCLUDED,
all evaluated on the SAME honest held-out slide (BFD_1):

  baseline            clean labels | vessel-centred | screened negatives
                      (= A_clean = B_vessel_centered = C_screened = pilot mosaic0)
  A_contam_matched    identical slides to baseline; the 2 slides that have BOTH a
                      clean and a fabricated .ndpa use their FABRICATED labels.
                      Controlled: only the labels change.
  A_contam_asitwas    the corpus as it stood BEFORE the audit (5 fabricated slides).
                      Realistic dose; confounded by slide list — reported as such.
  B_sliding_window    positives from the OLD sliding-window tiler; negatives held
                      constant (screened). Isolates tiling.
  C_blind_negatives   negatives unscreened (~35% hold real vessels); positives held
                      constant. Isolates negative-label noise.
  pilot_mosaic1       baseline data, mosaic=1.0 — the pilot's slow arm.

    python run_ablations.py --build          # build + assert conditions, no training
    python run_ablations.py --run baseline
    python run_ablations.py --run-all
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tiling_config as TC
from ablations import (BLIND, CONTAM, CORPUS, DUAL_SOURCE, HELD_OUT, OUT,
                       REQUIRED_HASH, SLIDING, STUDY_SCALES, assert_c1, assert_c3,
                       imgs_from, write_condition)

RIGOR = os.path.dirname(os.path.abspath(__file__))
HANDOFF = os.path.join(os.path.dirname(RIGOR), "handoff")
RUNS = os.path.join(HANDOFF, "runs")

EPOCHS = 300
PATIENCE = 60
SEED = 0
BATCH = 16


def git_commit():
    try:
        r = subprocess.run(["git", "-C", RIGOR, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else "no_git_repo"
    except Exception:
        return "no_git_repo"


# ── condition construction ───────────────────────────────────────────────────

def build_conditions():
    from slide_registry import load_clean_slides
    assert_c3()

    ratified = load_clean_slides()
    train_slides = sorted(s for s in ratified if s != HELD_OUT)   # 10 slides
    held = {HELD_OUT}

    # THE SHARED EVAL SET — identical for every condition.
    # BFD_1's clean, vessel-centred, hand-verified tiles. Only training varies.
    val = imgs_from(CORPUS, STUDY_SCALES, held)

    conds = {}

    # --- baseline: clean + vessel-centred + screened -------------------------
    conds["baseline"] = write_condition(
        "baseline",
        imgs_from(CORPUS, STUDY_SCALES, set(train_slides)),
        val)

    # --- A_contam_matched: same slides, fabricated labels on the 2 dual-source
    # slides. Positives for those 2 come from the CONTAMINATED corpus instead.
    # THIS IS THE CAUSAL COMPARISON: identical slides, identical tiler, identical
    # tiles — only the label source differs from `baseline`.
    swap = set(DUAL_SOURCE)
    clean_paired = imgs_from(CORPUS, STUDY_SCALES, swap, splits=("positives",))
    fabricated_paired = imgs_from(CONTAM, STUDY_SCALES, swap, splits=("positives",))
    tr = imgs_from(CORPUS, STUDY_SCALES, set(train_slides) - swap)            # clean
    tr += fabricated_paired                                                   # fabricated
    tr += imgs_from(CORPUS, STUDY_SCALES, swap, splits=("negatives",))        # neg constant
    conds["A_contam_matched"] = write_condition("A_contam_matched", tr, val)
    conds["A_contam_matched"]["n_paired_tiles"] = len(fabricated_paired)
    conds["baseline"]["n_paired_tiles"] = len(clean_paired)
    print(f"  {'paired label swap':<20} clean={len(clean_paired)} "
          f"fabricated={len(fabricated_paired)} tiles on {sorted(swap)}")

    # --- A_contam_asitwas: the pre-audit corpus (5 fabricated slides present) --
    lost = {"S.3152_26_A3FD_1", "A3_FD_1", "S.2016_26_A3_FD_1"}
    tr = imgs_from(CORPUS, STUDY_SCALES, set(train_slides) - swap)
    tr += imgs_from(CONTAM, STUDY_SCALES, swap | lost, splits=("positives",))
    tr += imgs_from(CORPUS, STUDY_SCALES, swap, splits=("negatives",))
    conds["A_contam_asitwas"] = write_condition("A_contam_asitwas", tr, val)

    # --- A_contam_fabval: THE CONTROLLED REPRODUCTION OF THE LEAK ------------
    # The brief's §1a story has TWO halves: contaminated training scores HIGH on its
    # own FABRICATED validation, and COLLAPSES on the honest slide. Evaluating only
    # on the honest slide shows a collapse with nothing to collapse *from*.
    #
    # So: train on the contaminated corpus with ONE fabricated slide held out
    # (S.3152_26_A3FD_1 — the slide that was 70% of fold 0's leaked validation),
    # then evaluate the SAME model twice:
    #   (a) on S.3152's FABRICATED tiles  -> expected HIGH  (machine labels are
    #       self-consistent: a model can learn another model's invented boxes)
    #   (b) on BFD_1's HONEST tiles       -> expected COLLAPSE
    # One model, two eval sets. That is the controlled version of the
    # 0.705/0.780 (leaked) vs honest contrast — an experiment, not an anecdote.
    fabval_slide = "S.3152_26_A3FD_1"
    tr = imgs_from(CORPUS, STUDY_SCALES, set(train_slides) - swap)
    tr += imgs_from(CONTAM, STUDY_SCALES,
                    (swap | lost) - {fabval_slide}, splits=("positives",))
    tr += imgs_from(CORPUS, STUDY_SCALES, swap, splits=("negatives",))
    conds["A_contam_fabval"] = write_condition("A_contam_fabval", tr, val)
    conds["A_contam_fabval"]["fabricated_eval_slide"] = fabval_slide

    # the SECOND eval set for that run: the held-out FABRICATED slide's tiles.
    # C1 still holds — this slide is NOT in its training set.
    fab_val_imgs = imgs_from(CONTAM, STUDY_SCALES, {fabval_slide},
                             splits=("positives",))
    fd = os.path.join(OUT, "A_contam_fabval")
    fvp = os.path.join(fd, "val_fabricated.txt")
    open(fvp, "w").write("\n".join(fab_val_imgs) + "\n")
    import yaml as _yaml
    fyp = os.path.join(fd, "data_fabricated_val.yaml")
    with open(fyp, "w") as fh:
        _yaml.safe_dump({"path": OUT, "train": os.path.join(fd, "train.txt"),
                         "val": fvp, "nc": 1, "names": ["blood_vessel"]},
                        fh, sort_keys=False)
    conds["A_contam_fabval"]["fabricated_val_yaml"] = fyp
    conds["A_contam_fabval"]["n_fabricated_val_images"] = len(fab_val_imgs)
    print(f"  {'fabricated-val eval':<20} {len(fab_val_imgs)} tiles from "
          f"{fabval_slide} (held OUT of its training) -> the 'leaked' score")

    # --- A_contam_heavy: FABRICATION-TRAINED -> held-out FABRICATED eval ------
    # The missing half of the inflation story. `A_contam_fabval` was clean-dominated
    # and could not show inflation (a model must be trained on a fabrication
    # distribution to reproduce it). Here we train predominantly on FABRICATED
    # labels (4 slides, single `10xv25` generation per the agreed design) and
    # evaluate on a FIFTH slide's fabricated tiles, held OUT of training (C1 holds),
    # PLUS the same honest BFD_1 slide every other condition uses.
    HEAVY = r"C:\placenta_ssd\tiles_contam_heavy"
    heavy_eval_slide = "S.3152_26_A3FD_1"
    heavy_train_slides = ["A2FD_1_S.2058_26", "A3_FD_1", "S.2016_26_A3_FD_1",
                          "S.2723_26_A2_FD_1"]
    heavy_tr = imgs_from(HEAVY, STUDY_SCALES, set(heavy_train_slides))
    conds["A_contam_heavy"] = write_condition("A_contam_heavy", heavy_tr, val)
    conds["A_contam_heavy"]["fabricated_eval_slide"] = heavy_eval_slide
    conds["A_contam_heavy"]["fabrication_generation"] = "10xv25 (single generation, train+eval)"

    heavy_fab_val_imgs = imgs_from(HEAVY, STUDY_SCALES, {heavy_eval_slide},
                                   splits=("positives",))
    hd = os.path.join(OUT, "A_contam_heavy")
    hvp = os.path.join(hd, "val_fabricated.txt")
    open(hvp, "w").write("\n".join(heavy_fab_val_imgs) + "\n")
    hyp = os.path.join(hd, "data_fabricated_val.yaml")
    with open(hyp, "w") as fh:
        _yaml.safe_dump({"path": OUT, "train": os.path.join(hd, "train.txt"),
                         "val": hvp, "nc": 1, "names": ["blood_vessel"]},
                        fh, sort_keys=False)
    conds["A_contam_heavy"]["fabricated_val_yaml"] = hyp
    conds["A_contam_heavy"]["n_fabricated_val_images"] = len(heavy_fab_val_imgs)
    print(f"  {'A_contam_heavy':<20} train={len(heavy_tr)} (4 fabricated slides) "
          f"fab-eval={len(heavy_fab_val_imgs)} ({heavy_eval_slide}, held OUT)")

    # --- B_sliding_window: old grid positives, screened negatives -------------
    tr = imgs_from(SLIDING, STUDY_SCALES, set(train_slides),
                   splits=("positives",), layout="nested")
    tr += imgs_from(CORPUS, STUDY_SCALES, set(train_slides), splits=("negatives",))
    conds["B_sliding_window"] = write_condition("B_sliding_window", tr, val)

    # --- C_blind_negatives: vessel-centred positives, UNSCREENED negatives ----
    # COUNT-MATCHED. Blind negatives reach 1:1 easily, but the screened ones fall
    # short (vessel-free placental tissue is genuinely rare). Left unmatched, this
    # condition would carry ~21% MORE training images than baseline, and a recall
    # drop could not be attributed to label noise rather than to data volume.
    # So we subsample the blind pool to the SAME count per (slide, scale) as the
    # screened set. Only negative QUALITY varies; quantity is pinned.
    import random as _rnd
    tr = imgs_from(CORPUS, STUDY_SCALES, set(train_slides), splits=("positives",))
    n_matched = 0
    for sc in STUDY_SCALES:
        for sid in train_slides:
            k = len(imgs_from(CORPUS, [sc], {sid}, splits=("negatives",)))
            pool = imgs_from(BLIND, [sc], {sid}, splits=("negatives",))
            _rnd.Random(f"{sid}|{sc}|match").shuffle(pool)
            tr += pool[:k]
            n_matched += min(k, len(pool))
    conds["C_blind_negatives"] = write_condition("C_blind_negatives", tr, val)
    conds["C_blind_negatives"]["n_negatives_count_matched"] = n_matched
    print(f"  {'count-matched':<20} blind negatives subsampled to {n_matched} "
          f"(= the screened count), so only QUALITY varies")

    with open(os.path.join(OUT, "conditions.json"), "w") as fh:
        json.dump(conds, fh, indent=2)
    return conds


# ── training ─────────────────────────────────────────────────────────────────

def train(name, mosaic=0.0, epochs=EPOCHS):
    import warnings
    warnings.filterwarnings("ignore")
    import ultralytics
    from ultralytics import YOLO

    hash_ = assert_c3()
    conds = json.load(open(os.path.join(OUT, "conditions.json")))
    key = "baseline" if name == "pilot_mosaic1" else name
    c = conds[key]

    d = os.path.join(OUT, key)
    tr_txt, va_txt = os.path.join(d, "train.txt"), os.path.join(d, "val.txt")
    train_slides, val_slides = assert_c1(tr_txt, va_txt, name)   # aborts on violation

    out_dir = os.path.join(RUNS, name)
    os.makedirs(out_dir, exist_ok=True)

    cfg = dict(data=c["yaml"], epochs=epochs, imgsz=TC.TILE_SIZE, batch=BATCH,
               device=0, seed=SEED, patience=PATIENCE, workers=8,
               deterministic=True, mosaic=mosaic, mixup=0.0, copy_paste=0.0,
               hsv_h=0.005, hsv_s=0.05, hsv_v=0.10,
               project=RUNS, name=name, exist_ok=True, verbose=False, plots=False)

    manifest = {
        "run": name, "condition": key, "seed": SEED,
        "tiling_hash": hash_, "tiling_method": TC.METHOD,
        "held_out_slide": HELD_OUT,
        "held_out_rationale": ("originally clean — never fabricated, never "
                               "recovered; 334 eval positives at all 3 scales"),
        "train_slides": train_slides, "val_slides": val_slides,
        "n_train_images": c["n_train"], "n_val_images": c["n_val"],
        "scales": list(STUDY_SCALES), "note_5x": "EXCLUDED per brief",
        "arch": "single_allmag", "mosaic": mosaic,
        "dataset_yaml": os.path.basename(c["yaml"]),
        "git_commit": git_commit(),
        "ultralytics": ultralytics.__version__,
        "python": platform.python_version(),
        "command": f"python run_ablations.py --run {name}",
        "config": {k: v for k, v in cfg.items() if k != "data"},
    }
    # provenance for the CAUSAL sub-run: the paired clean/fabricated tile swap.
    # Same slides, same tiler, same tiles — ONLY the label source differs.
    if key in ("baseline", "A_contam_matched"):
        manifest["paired_label_swap"] = {
            "design": ("controlled: identical slide list, identical vessel_centered_v3 "
                       "tiles; only the LABEL SOURCE differs between the two runs"),
            "swapped_slides": DUAL_SOURCE,
            "n_paired_tiles": c.get("n_paired_tiles"),
            "label_source_this_run": ("clean pathologist .ndpa" if key == "baseline"
                                      else "machine-written (fabricated) .ndpa"),
            "clean_ndpa": {
                "A2FD_1_S.2058_26": "PLACENTA SLIDES/A Files/A2FD 1 S.2058 26.ndpi.ndpa (200 boxes, CLEAN)",
                "S.2723_26_A2_FD_1": "PLACENTA SLIDES/A Files/S.2723 26 A2 FD 1.ndpi.ndpa (27 boxes, CLEAN)",
            },
            "fabricated_ndpa": {
                "A2FD_1_S.2058_26": "PLACENTA SLIDES/placenta/annotaions/10xv25/A2FD 1 S.2058 26.ndpi.ndpa (194 boxes, GENERATED)",
                "S.2723_26_A2_FD_1": "PLACENTA SLIDES/placenta/annotaions/10xv25/S.2723 26 A2 FD 1.ndpi.ndpa (77 boxes, GENERATED)",
            },
            "note": ("this pair is the CAUSAL comparison. A_contam_asitwas is the "
                     "realistic-magnitude comparison but is confounded: it carries 3 "
                     "extra training slides (the permanently-lost ones)."),
        }
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"\n=== {name} | mosaic={mosaic} | train={c['n_train']} val={c['n_val']} "
          f"| held-out={HELD_OUT} ===", flush=True)
    t0 = time.time()
    YOLO("yolo11n.pt").train(**cfg)
    dt = time.time() - t0

    # headline metrics on the held-out slide, and the epoch each peaked at
    import csv
    rows = list(csv.DictReader(open(os.path.join(out_dir, "results.csv"))))
    def peak(col):
        b = max(rows, key=lambda r: float(r[col]))
        return float(b[col]), int(float(b["epoch"]))
    m50, e50 = peak("metrics/mAP50(B)")
    m95, e95 = peak("metrics/mAP50-95(B)")
    last = rows[-1]
    final = {
        "run": name, "held_out_slide": HELD_OUT,
        "mAP50": m50, "mAP50_at_epoch": e50,
        "mAP50_95": m95, "mAP50_95_at_epoch": e95,
        "precision_at_best_mAP50": float(
            next(r for r in rows if int(float(r["epoch"])) == e50)["metrics/precision(B)"]),
        "recall_at_best_mAP50": float(
            next(r for r in rows if int(float(r["epoch"])) == e50)["metrics/recall(B)"]),
        "epochs_run": int(float(last["epoch"])),
        "seconds_per_epoch": dt / max(1, int(float(last["epoch"]))),
        "seed": SEED, "mosaic": mosaic,
    }
    # SECOND EVALUATION for A_contam_fabval: the same model, scored on its OWN
    # FABRICATED validation slide (held out of its training, so C1 still holds).
    # This is the "leaked" number — the one that made the original pipeline look
    # good. Reported ALONGSIDE the honest collapse, never as a valid score.
    if key in ("A_contam_fabval", "A_contam_heavy") and c.get("fabricated_val_yaml"):
        best = os.path.join(out_dir, "weights", "best.pt")
        m = YOLO(best).val(data=c["fabricated_val_yaml"], imgsz=TC.TILE_SIZE,
                           batch=BATCH, device=0, verbose=False, plots=False,
                           project=out_dir, name="val_fabricated", exist_ok=True)
        rd = m.results_dict
        note = ("this model was trained PREDOMINANTLY ON FABRICATED LABELS (4 "
                "slides, single 10xv25 generation). A high score here would be "
                "self-consistency — the model reproducing this generator's own "
                "invented boxes on a genuinely held-out slide from the SAME "
                "generation. Compare with the honest BFD_1 score above."
                if key == "A_contam_heavy" else
                "this is the INFLATED score — the model is graded against another "
                "model's invented boxes. Compare it with the honest held-out score "
                "above. It is the controlled reproduction of the 0.705/0.780 leak, "
                "and is NOT a valid measure of detection quality.")
        final["fabricated_val"] = {
            "eval_slide": c["fabricated_eval_slide"],
            "eval_tiles": c["n_fabricated_val_images"],
            "labels": "MACHINE-GENERATED (fabricated) — NOT valid ground truth",
            "mAP50": float(rd.get("metrics/mAP50(B)", 0)),
            "mAP50_95": float(rd.get("metrics/mAP50-95(B)", 0)),
            "precision": float(rd.get("metrics/precision(B)", 0)),
            "recall": float(rd.get("metrics/recall(B)", 0)),
            "interpretation": note,
        }
        print(f"\n--- SAME MODEL, evaluated on its own FABRICATED validation ({key}) ---")
        print(json.dumps(final["fabricated_val"], indent=2))

    with open(os.path.join(out_dir, "metrics_final.json"), "w") as fh:
        json.dump(final, fh, indent=2)
    print(json.dumps(final, indent=2))
    return final


ORDER = ["baseline", "A_contam_matched", "A_contam_asitwas", "A_contam_fabval",
         "B_sliding_window", "C_blind_negatives", "pilot_mosaic1", "A_contam_heavy"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--run")
    ap.add_argument("--run-all", action="store_true")
    a = ap.parse_args()

    if a.build:
        print(f"C3 ok — {assert_c3()}\nheld-out: {HELD_OUT}\n")
        build_conditions()
    elif a.run:
        train(a.run, mosaic=1.0 if a.run == "pilot_mosaic1" else 0.0)
    elif a.run_all:
        # SINGLE-INSTANCE LOCK.
        # Two supervisors were once alive at the same time; each spawned its own
        # `--run-all`. Both picked the same next-incomplete run, both wrote to the
        # SAME output directory, and they clobbered each other — one reset the
        # other's training from epoch 81 back to epoch 1. Silent, and it would have
        # corrupted whichever run happened to be in flight.
        # An exclusive file lock makes a second instance exit immediately.
        LOCK = os.path.join(RUNS, ".runner.lock")
        os.makedirs(RUNS, exist_ok=True)
        try:
            _lock = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(_lock, str(os.getpid()).encode())
        except FileExistsError:
            try:
                held = open(LOCK).read().strip()
                alive = subprocess.run(["tasklist", "/FI", f"PID eq {held}"],
                                       capture_output=True, text=True).stdout
                if held and held in alive:
                    print(f"ANOTHER RUNNER IS ALREADY ACTIVE (pid {held}) — exiting. "
                          f"Two runners would clobber the same run directory.")
                    sys.exit(0)
            except Exception:
                pass
            print("stale lock found (holder is dead) — taking over")
            os.remove(LOCK)
            _lock = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(_lock, str(os.getpid()).encode())
        import atexit
        atexit.register(lambda: os.path.exists(LOCK) and os.remove(LOCK))

        # EACH RUN IN ITS OWN PROCESS.
        # Training them all in one process OOM'd on run 2: PyTorch does not fully
        # release VRAM between successive Ultralytics trainings in the same
        # interpreter, so allocations accumulate until the card is exhausted.
        # (The GPU was completely free the instant the process died — nothing
        # external was holding memory.) A fresh process per run reclaims all of it.
        for n in ORDER:
            done = os.path.join(RUNS, n, "metrics_final.json")
            if os.path.exists(done):
                print(f"skip {n} (already complete)", flush=True)
                continue
            print(f"\n>>> launching {n} in a fresh process", flush=True)
            r = subprocess.run([sys.executable, os.path.abspath(__file__),
                                "--run", n], cwd=RIGOR)
            if r.returncode != 0:
                print(f"!!! {n} FAILED (exit {r.returncode}) — continuing to next run",
                      flush=True)
    else:
        ap.print_help()
