"""
build_heavy.py — the fabrication-TRAINED condition (A_contam_heavy).

PURPOSE
`A_contam_fabval` came out backwards: a clean-dominated model scored 0.882 on real
labels and only 0.124 on fabricated ones. That shows the fabricated labels are
substantially fictional — but it does NOT show that fabrication *inflates* scores,
because a model must be trained on a fabrication distribution before it can
reproduce it.

This condition supplies the missing half:
    train PREDOMINANTLY on fabricated labels
    -> evaluate on HELD-OUT fabricated tiles  (expected: HIGH — self-consistency)
    -> evaluate on the honest slide           (expected: LOW  — no real skill)

Together with `A_contam_fabval` that is the full two-sided story, and it is what
converts the original 0.705 leak from an anecdote into a controlled result.

TWO CONDITIONS ON THIS RUN (both enforced here)

1. ONE FABRICATION GENERATION THROUGHOUT.
   `S.3152_26_A3FD_1` has FOUR different fabricated .ndpa on disk (301 / 131 / 146 /
   298 boxes, from different inference runs). The corpus built earlier used the
   301-box `A Files` copy for that slide but the `10xv25` copies for the others —
   so a model would have trained on one generation and been graded against another,
   destroying the self-consistency test.
   `10xv25` is the only directory carrying fabricated .ndpa for ALL five slides, so
   everything here — train AND eval — uses `10xv25`. The exact source path and box
   count for every slide is written into the run manifest.

2. GENUINELY HELD-OUT FABRICATED EVAL.
   The eval slide (`S.3152_26_A3FD_1`) is NOT in the training set. If it were, a high
   score would be memorisation — the very failure we are documenting. C1 holds for
   both eval sets.

WE DO NOT CLAIM TO REPRODUCE 0.705. The original run's .ndpa copy is unknown, so our
number stands on its own as a controlled result, not as a replication.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths

HEAVY = paths.TILES_CONTAM_HEAVY
CONTAM_DIR = paths.SLIDES_CONTAM
CLEAN_SLIDES = paths.SLIDES
STUDY_SCALES = ("10x", "20x", "40x")

# ALL from the 10xv25 generation — one generator, train and eval alike.
GEN = "10xv25"
SOURCES = {
    # slide_id: (ndpi filename, fabricated ndpa filename, box count, role)
    "A3_FD_1":           ("A3 FD 1.ndpi",           "A3 FD 1.ndpi.ndpa",            67, "train"),
    "S.2016_26_A3_FD_1": ("S.2016 26 A3 FD 1.ndpi", "S.2016 26 A3 FD 1.ndpi.ndpa",  25, "train"),
    "A2FD_1_S.2058_26":  ("A2FD 1 S.2058 26.ndpi",  "A2FD 1 S.2058 26.ndpi.ndpa",  194, "train"),
    "S.2723_26_A2_FD_1": ("S.2723 26 A2 FD 1.ndpi", "S.2723 26 A2 FD 1.ndpi.ndpa",  77, "train"),
    # HELD OUT — the fabricated eval set. Never seen in training.
    "S.3152_26_A3FD_1":  ("S.3152 26 A3FD 1.ndpi",  "S.3152 26 A3FD 1_10xv25.ndpi.ndpa", 131, "EVAL"),
}


def find_ndpi(name):
    for d in (CONTAM_DIR, CLEAN_SLIDES):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def main():
    import warnings
    warnings.filterwarnings("ignore")
    from tile_vessel_centered import extract_slide_scale

    print(f"Fabrication generation: {GEN} (single generation for BOTH train and eval)\n")
    print(f"{'slide':<22}{'role':>6}{'boxes':>7}{'scale':>6}{'tiles':>7}")
    print("-" * 50)

    t0 = time.time()
    totals = {"train": 0, "EVAL": 0}
    for sid, (ndpi_name, ndpa_name, boxes, role) in SOURCES.items():
        ndpi = find_ndpi(ndpi_name)
        ndpa = os.path.join(CONTAM_DIR, ndpa_name)
        if not ndpi or not os.path.exists(ndpa):
            print(f"{sid:<22}  MISSING (ndpi={bool(ndpi)} ndpa={os.path.exists(ndpa)})")
            continue
        for sc in STUDY_SCALES:
            p, _ = extract_slide_scale(ndpi, ndpa, sid, sc, HEAVY, 0, False)
            print(f"{sid:<22}{role:>6}{boxes:>7}{sc:>6}{p:>7}", flush=True)
            totals[role] += p

    print("-" * 50)
    print(f"fabricated TRAIN tiles: {totals['train']}")
    print(f"fabricated EVAL  tiles: {totals['EVAL']}  (held-out slide S.3152_26_A3FD_1)")
    print(f"\n-> {HEAVY}   ({(time.time()-t0)/60:.1f} min)")


if __name__ == "__main__":
    main()
