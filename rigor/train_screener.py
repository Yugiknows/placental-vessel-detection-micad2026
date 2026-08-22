"""
train_screener.py — train the high-recall detector used to SCREEN negative tiles.

Not part of the experiment. Its only job is to look at a candidate background tile
and say "there is a vessel in here" so we can throw that tile away.

WHY IT EXISTS: the pre-contamination model (blood_vessel_best_BACKUP.pt) has only
78-92% recall on this corpus — it is blind to ~1 in 10 vessels, and the user could
still SEE vessels in tiles it had passed as clean. A screener must have very high
recall or it silently ships negatives containing visible vessels, which teaches
the detector that a vessel IS background and suppresses the exact recall the
paper's claim is measured on.

This trains on the user's 3,594 hand-reviewed positive tiles (all scales pooled),
so unlike the old backup model it knows exactly what THESE vessels look like at
THESE magnifications. It is combined with the trusted model as a UNION at
screening time — a vessel must fool both.

NOTE: must be a real .py file, not piped via stdin. Ultralytics' dataloader
spawns workers, and Windows `spawn` re-imports __main__ from its path; with a
heredoc that path is the literal '<stdin>' and every worker dies with
OSError: [Errno 22] Invalid argument.

    python train_screener.py
"""

import warnings

warnings.filterwarnings("ignore")

from ultralytics import YOLO

import paths

DATA = paths.SCREENER_YAML
OUT = paths.SCREENER_DIR


def main():
    model = YOLO("yolo11n.pt")
    model.train(
        data=DATA,
        # 35, not 60: this is a SCREENER, not a model under test. It only has to
        # fire on vessels at conf=0.01, which converges long before mAP does.
        epochs=35,
        imgsz=1024,          # keep 1024 — at 40x a small vessel is ~15px, and
                             # downscaling would cost exactly the recall we need
        # Measured mid-run: GPU pinned at 96% util but only 3.9GB of 8.2GB VRAM
        # in use. The card was half idle at batch=8. 16 fills it.
        batch=16,
        device=0,
        seed=0,
        patience=10,
        workers=8,           # 8 physical cores; feeds the larger batches
        cache="disk",        # decode each PNG once, not once per epoch
        verbose=True,
        plots=False,
        # No geometric/colour mixing: we want a faithful vessel detector, and
        # mosaic is the very thing under test in the main experiment.
        mosaic=0.0,
        mixup=0.0,
        copy_paste=0.0,
        hsv_s=0.05,
        project=OUT,
        name="run",
        exist_ok=True,
    )
    print("SCREENER_TRAINING_DONE")


if __name__ == "__main__":
    main()
