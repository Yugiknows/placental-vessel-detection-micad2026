"""
ablations.py — build the corpus-ablation conditions (MICAD handoff, §1a).

ONE honest held-out slide is fixed for EVERY condition so the numbers are directly
comparable:

    HELD_OUT = BFD_1
      * originally clean — never fabricated, never recovered
      * 334 eval positives, vessels at all three scales (37/162/135)
      * the larger eligible slide (S.2_723_26_A3_FD_1, 1517) is 43% of the whole
        corpus; holding it out would cripple training and confound everything

EVERY condition is EVALUATED on the SAME held-out tiles — BFD_1's clean,
vessel-centred, hand-verified tiles. Only the TRAINING data changes. Otherwise a
"tiling" ablation would also change the test set and measure nothing.

Conditions (all: single_allmag, mosaic=0, seed=0, 10x/20x/40x, 5x EXCLUDED):

  BASELINE          clean labels + vessel-centred tiles + screened negatives
                    (also serves as A_clean, B_vessel_centered, C_screened,
                     and the pilot's mosaic=0 arm)

  A_contaminated    same tiler, same held-out, but training labels come from the
                    MACHINE-WRITTEN .ndpa — plus the 3 permanently-lost slides put
                    back. This is the corpus as it stood BEFORE the audit.
                    Confound to report: it has 3 more training slides than the
                    clean condition, because those slides were later dropped.

  A_contam_matched  the CONTROLLED version: identical slide list to BASELINE, but
                    the 2 slides that have BOTH a clean and a fabricated .ndpa
                    (A2FD_1_S.2058_26, S.2723_26_A2_FD_1) use their FABRICATED
                    labels. Same slides, same tiles, only the labels differ — so
                    any gap is attributable to fabrication alone.

  B_sliding_window  positives from the OLD whole-slide sliding-window tiler
                    (vessel on the tile edge in 58% of positives), negatives held
                    CONSTANT (the screened ones) so this isolates tiling.

  C_blind_negatives positives held CONSTANT (vessel-centred), negatives are the
                    UNSCREENED ones (~35% contain real, unlabelled vessels), so
                    this isolates negative-label noise.

C1 and C3 are asserted before anything is written.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tiling_config as TC

REQUIRED_HASH = "7b191fa9e02e"
HELD_OUT = "BFD_1"

CORPUS = r"C:\placenta_ssd\tiles_v3"                 # ratified, hand-reviewed
SLIDING = r"C:\placenta_ssd\training_clean"          # the OLD sliding-window tiles
CONTAM = r"C:\placenta_ssd\tiles_contaminated"       # built by --build-contaminated
BLIND = r"C:\placenta_ssd\tiles_blind_neg"           # built by --build-blind-negatives
OUT = r"C:\placenta_ssd\ablations"

STUDY_SCALES = ("10x", "20x", "40x")                 # 5x EXCLUDED (brief §0.2)

# Slides whose .ndpa was destroyed and replaced by model output.
FABRICATED = {
    "S.3152_26_A3FD_1":   "A Files/S.3152 26 A3FD 1.ndpi.ndpa",
    "A3_FD_1":            "placenta/annotaions/10xv25/A3 FD 1.ndpi.ndpa",
    "S.2016_26_A3_FD_1":  "placenta/annotaions/10xv25/S.2016 26 A3 FD 1.ndpi.ndpa",
    "A2FD_1_S.2058_26":   "placenta/annotaions/10xv25/A2FD 1 S.2058 26.ndpi.ndpa",
    "S.2723_26_A2_FD_1":  "placenta/annotaions/10xv25/S.2723 26 A2 FD 1.ndpi.ndpa",
}
# of those, the two that ALSO have a surviving clean .ndpa -> controlled swap
DUAL_SOURCE = ["A2FD_1_S.2058_26", "S.2723_26_A2_FD_1"]
# the three with no clean .ndpa anywhere -> only exist in the contaminated corpus
LOST_ONLY = ["S.3152_26_A3FD_1", "A3_FD_1", "S.2016_26_A3_FD_1"]

SLIDES_DRIVE = r"D:\PLACENTA SLIDES"


# ── guards ───────────────────────────────────────────────────────────────────

def assert_c3():
    from tiling_fingerprint import fingerprint
    h = fingerprint()["tiling_hash"]
    if h != REQUIRED_HASH:
        sys.exit(f"C3 ABORT: corpus hash is {h}, brief requires {REQUIRED_HASH}")
    return h


def slide_of(stem):
    for sc in TC.ALL_SCALES:
        m = f"_{sc}_"
        i = stem.rfind(m)
        if i != -1:
            return stem[:i]
    return None


def assert_c1(train_txt, val_txt, label):
    def slides(p):
        s = set()
        for ln in open(p, encoding="utf-8"):
            ln = ln.strip()
            if ln:
                s.add(slide_of(os.path.splitext(os.path.basename(ln))[0]))
        s.discard(None)
        return s

    tr, ev = slides(train_txt), slides(val_txt)
    shared = tr & ev
    if shared:
        sys.exit(f"C1 ABORT [{label}]: slide(s) in BOTH train and eval: {sorted(shared)}")
    if ev != {HELD_OUT}:
        sys.exit(f"C1 ABORT [{label}]: eval must be exactly {{{HELD_OUT}}}, got {sorted(ev)}")
    return sorted(tr), sorted(ev)


# ── listing helpers ──────────────────────────────────────────────────────────

def imgs_from(root, scales, slides, splits=("positives", "negatives"),
              layout="flat"):
    """layout 'flat'   -> training_data_X/{positives,negatives}/images  (tiles_v3)
       layout 'nested' -> training_data_X/train/{positives,negatives}/images (sliding)"""
    out = []
    for sc in scales:
        for sp in splits:
            if layout == "flat":
                d = os.path.join(root, f"training_data_{sc}", sp, "images")
            else:
                d = os.path.join(root, f"training_data_{sc}", "train", sp, "images")
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if f.endswith(".png") and slide_of(os.path.splitext(f)[0]) in slides:
                    out.append(os.path.join(d, f))
    return out


def write_condition(name, train_imgs, val_imgs, out_root=OUT):
    import yaml
    d = os.path.join(out_root, name)
    os.makedirs(d, exist_ok=True)
    tp, vp = os.path.join(d, "train.txt"), os.path.join(d, "val.txt")
    open(tp, "w").write("\n".join(train_imgs) + "\n")
    open(vp, "w").write("\n".join(val_imgs) + "\n")
    tr, ev = assert_c1(tp, vp, name)
    yp = os.path.join(d, "data.yaml")
    with open(yp, "w") as fh:
        yaml.safe_dump({"path": out_root, "train": tp, "val": vp,
                        "nc": 1, "names": ["blood_vessel"]}, fh, sort_keys=False)
    print(f"  {name:<20} train={len(train_imgs):>5} val={len(val_imgs):>4} "
          f"| {len(tr)} train slides | C1 ok")
    return {"name": name, "yaml": yp, "n_train": len(train_imgs),
            "n_val": len(val_imgs), "train_slides": tr, "val_slides": ev}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    h = assert_c3()
    print(f"C3 ok — corpus hash {h}\nheld-out slide: {HELD_OUT}\n")
