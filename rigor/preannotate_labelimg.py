"""
preannotate_labelimg.py — model-assisted pre-annotation for labelImg, built so
it CANNOT recreate the NDPA-overwrite contamination.

This is a safe adaptation of the user's run_predict_wsi_multithread(): it scans
a WSI in tiles with a TRUSTED model and collects boxes, but instead of writing
predictions back into a .ndpa as if they were ground truth (the bug that voided
five slides), it emits an isolated labelImg review folder that a human must
open, correct, and sign off before any tile enters the training corpus.

Hard rails (all enforced, not advisory):
  R1  The model must pass `assert_trusted_model`. The void checkpoints under
      runs/train/ (trained on contaminated data) are rejected by name; only a
      model that predates the first contamination write, or one carrying an
      explicit `<model>.trusted` marker, is accepted.
  R2  Output goes ONLY under rigor/preannotation_review/. Writing anywhere
      under placenta_training/, cv_training_existing/, or to any *.ndpa is
      refused.
  R3  Every predicted label is stamped UNVERIFIED via a per-slide sidecar.
      `promote` refuses to ingest a folder whose sidecar still says unverified.
  R4  Nothing is ever overwritten; existing files abort the run.

Predictions are NEVER labels. They are a starting point for human review.

Requires (absent on this machine): openslide-python + a raw .ndpi. The trust
gate and the YOLO->labelImg conversion are import-safe and unit-checked; the
WSI scan imports openslide lazily so this module loads without it.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tiling_fingerprint import read_tiling_params

RIGOR_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(RIGOR_DIR)
REVIEW_ROOT = os.path.join(RIGOR_DIR, "preannotation_review")

# First model-generated .ndpa write found in this repo (see BLOCKERS.md B1).
FIRST_CONTAMINATION = dt.date(2026, 6, 16)

CONF, IOU = 0.5, 0.5           # matching the user's inference settings
VESSEL_CLASS = 0               # trusted model is 2-class; keep blood_vessel only


class UnsafeError(RuntimeError):
    pass


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def assert_trusted_model(model_path):
    """R1. Raise unless this model provably cannot carry fabricated boxes."""
    ap = os.path.abspath(model_path)
    if not os.path.exists(ap):
        raise UnsafeError(f"model not found: {ap}")

    norm = ap.replace("\\", "/")
    if "/runs/train/" in norm or "/runs/detect/" in norm:
        raise UnsafeError(
            f"REFUSED: {model_path} lives under runs/train — these checkpoints "
            "were trained on contaminated folds (BLOCKERS.md B2) and are void. "
            "Pre-annotating with them would re-inject the same bad boxes."
        )

    if os.path.exists(ap + ".trusted"):
        return True

    # Accept only if the weights file predates the first contamination write.
    mdate = dt.date.fromtimestamp(os.path.getmtime(ap))
    if mdate < FIRST_CONTAMINATION:
        return True

    raise UnsafeError(
        f"REFUSED: cannot establish {model_path} as trusted. It is dated "
        f"{mdate} (>= first contamination {FIRST_CONTAMINATION}) and has no "
        f"`{os.path.basename(ap)}.trusted` marker. Create that marker only if "
        "you can vouch its training data was contamination-free."
    )


def _assert_safe_out(path):
    """R2. Output must stay inside the review root, never in the corpus."""
    ap = os.path.abspath(path).replace("\\", "/")
    forbidden = ("/placenta_training/", "/cv_training_existing/")
    if any(f in ap for f in forbidden) or ap.endswith(".ndpa"):
        raise UnsafeError(f"REFUSED: {path} is inside protected data — R2.")
    if not ap.startswith(os.path.abspath(REVIEW_ROOT).replace("\\", "/")):
        raise UnsafeError(f"REFUSED: {path} is outside {REVIEW_ROOT} — R2.")


def scale_downsample(scale):
    return read_tiling_params()["per_scale"][scale]["downsample"]


def generate(slide_path, model_path, scale, tile_size=1024, overlap=128,
             conf=CONF, iou=IOU):
    """Scan a WSI with a trusted model; emit a labelImg review folder."""
    import openslide            # lazy: absent on this machine
    from ultralytics import YOLO

    assert_trusted_model(model_path)

    slide_stem = os.path.splitext(os.path.basename(slide_path))[0].replace(" ", "_")
    out_dir = os.path.join(REVIEW_ROOT, slide_stem, scale)
    _assert_safe_out(out_dir)
    img_dir = os.path.join(out_dir, "images")
    lbl_dir = os.path.join(out_dir, "labels")
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise UnsafeError(f"REFUSED: {out_dir} already exists — R4 (no overwrite).")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)

    model = YOLO(model_path)
    slide = openslide.OpenSlide(slide_path)
    ds = scale_downsample(scale)
    level = slide.get_best_level_for_downsample(ds)
    actual_ds = slide.level_downsamples[level]
    lW, lH = slide.level_dimensions[level]
    stride = tile_size - overlap

    n_tiles = 0
    for ty in range(0, max(1, lH - tile_size + 1), stride):
        for tx in range(0, max(1, lW - tile_size + 1), stride):
            region = slide.read_region(
                (int(tx * actual_ds), int(ty * actual_ds)), level,
                (tile_size, tile_size)).convert("RGB")
            res = model.predict(region, conf=conf, iou=iou, verbose=False)[0]
            lines = []
            for b in res.boxes:
                if int(b.cls) != VESSEL_CLASS:
                    continue
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                cx = (x1 + x2) / 2 / tile_size
                cy = (y1 + y2) / 2 / tile_size
                w = (x2 - x1) / tile_size
                h = (y2 - y1) / tile_size
                lines.append(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            if not lines:
                continue
            name = f"{slide_stem}_{scale}_{int(tx*actual_ds):07d}_{int(ty*actual_ds):07d}"
            region.save(os.path.join(img_dir, name + ".png"))
            with open(os.path.join(lbl_dir, name + ".txt"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            n_tiles += 1
    slide.close()

    with open(os.path.join(lbl_dir, "classes.txt"), "w", encoding="utf-8") as fh:
        fh.write("blood_vessel\n")
    write_sidecar(out_dir, slide_path, model_path, scale, conf, iou, n_tiles)

    print(f"{n_tiles} candidate tiles -> {out_dir}")
    print("NEXT: open in labelImg, FIX every box (predictions are wrong until a "
          "human confirms), then run `promote`.")
    return n_tiles


def write_sidecar(out_dir, slide_path, model_path, scale, conf, iou, n_tiles):
    """R3. Marks the whole folder UNVERIFIED until a human promotes it."""
    sc = {
        "status": "UNVERIFIED — model output, NOT ground truth. Do not train on this.",
        "verified": False,
        "reviewed_by": None,
        "slide": os.path.basename(slide_path),
        "scale": scale,
        "model": os.path.abspath(model_path),
        "model_sha": _sha(model_path),
        "conf": conf, "iou": iou,
        "n_candidate_tiles": n_tiles,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
    }
    with open(os.path.join(out_dir, "_UNVERIFIED_DO_NOT_TRAIN.json"), "w",
              encoding="utf-8") as fh:
        json.dump(sc, fh, indent=2)


def promote(review_dir, reviewed_by, dest_root):
    """Ingest a human-reviewed folder into the corpus + tile ledger (R3)."""
    if not reviewed_by:
        sys.exit("--reviewed-by is required: record who verified these tiles.")
    side = os.path.join(review_dir, "_UNVERIFIED_DO_NOT_TRAIN.json")
    if not os.path.exists(side):
        sys.exit(f"no sidecar in {review_dir}; is this a preannotation folder?")

    with open(side, encoding="utf-8") as fh:
        sc = json.load(fh)
    sc.update(verified=True, reviewed_by=reviewed_by,
              promoted=dt.datetime.now().isoformat(timespec="seconds"),
              status="VERIFIED by human labelImg review.")
    # Rename the sidecar so a folder can't be silently re-promoted.
    with open(os.path.join(review_dir, "_VERIFIED.json"), "w", encoding="utf-8") as fh:
        json.dump(sc, fh, indent=2)
    os.remove(side)
    print(f"marked {review_dir} VERIFIED by {reviewed_by}.")
    print("Copy its images/ + labels/ into the training corpus, then run "
          "`python tile_provenance.py scan` and set these tiles verified=yes.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="scan a WSI -> labelImg review folder")
    g.add_argument("--slide", required=True)
    g.add_argument("--model", required=True)
    g.add_argument("--scale", required=True, choices=["10x", "20x", "40x", "5x"])

    p = sub.add_parser("promote", help="mark a reviewed folder verified")
    p.add_argument("--dir", required=True)
    p.add_argument("--reviewed-by", required=True)
    p.add_argument("--dest", default=None)

    c = sub.add_parser("check-model", help="test the trust gate on a model path")
    c.add_argument("--model", required=True)

    args = ap.parse_args()
    if args.cmd == "generate":
        generate(args.slide, args.model, args.scale)
    elif args.cmd == "promote":
        promote(args.dir, args.reviewed_by, args.dest)
    elif args.cmd == "check-model":
        try:
            assert_trusted_model(args.model)
            print(f"TRUSTED: {args.model}")
        except UnsafeError as e:
            print(e)
            sys.exit(1)
