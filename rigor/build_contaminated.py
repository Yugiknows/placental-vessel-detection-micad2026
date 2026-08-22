"""
build_contaminated.py — tile the FABRICATED labels (for ablation A).

Reads the MACHINE-WRITTEN .ndpa (the ones run_inference.py wrote over the
pathologist's annotations) and tiles them with the IDENTICAL vessel_centered_v3
method used for the clean corpus. Same tiler, same gates, same seed — the ONLY
thing that differs is that the labels are invented.

That is what makes ablation A a controlled comparison rather than an anecdote:
any performance gap on the honest held-out slide is attributable to the labels,
not to the tiling.

Output: C:\placenta_ssd\tiles_contaminated  (positives only; negatives are held
constant across conditions and come from the ratified corpus).
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tiling_config as TC
from ablations import CONTAM, FABRICATED, STUDY_SCALES

CLEAN_SLIDES_DIR = r"C:\placenta_ssd\slides"
CONTAM_DIR = r"C:\placenta_ssd\slides_contam"

# slide_id -> (ndpi filename, fabricated ndpa filename)
SOURCES = {
    "S.3152_26_A3FD_1":  ("S.3152 26 A3FD 1.ndpi",   "S.3152 26 A3FD 1.ndpi.ndpa"),
    "A3_FD_1":           ("A3 FD 1.ndpi",            "A3 FD 1.ndpi.ndpa"),
    "S.2016_26_A3_FD_1": ("S.2016 26 A3 FD 1.ndpi",  "S.2016 26 A3 FD 1.ndpi.ndpa"),
    "A2FD_1_S.2058_26":  ("A2FD 1 S.2058 26.ndpi",   "A2FD 1 S.2058 26.ndpi.ndpa"),
    "S.2723_26_A2_FD_1": ("S.2723 26 A2 FD 1.ndpi",  "S.2723 26 A2 FD 1.ndpi.ndpa"),
}


def find_ndpi(fname):
    for d in (CONTAM_DIR, CLEAN_SLIDES_DIR):
        p = os.path.join(d, fname)
        if os.path.exists(p):
            return p
    return None


def main():
    import warnings
    warnings.filterwarnings("ignore")
    from tile_vessel_centered import extract_slide_scale

    print("Tiling the FABRICATED labels with vessel_centered_v3.")
    print("Same tiler as the clean corpus — only the annotations are invented.\n")
    print(f"{'slide':<22}{'scale':>6}{'pos':>6}  (fabricated boxes)")
    print("-" * 50)

    t0 = time.time()
    total = 0
    for sid, (ndpi_name, ndpa_name) in SOURCES.items():
        ndpi = find_ndpi(ndpi_name)
        ndpa = os.path.join(CONTAM_DIR, ndpa_name)
        if not ndpi or not os.path.exists(ndpa):
            print(f"{sid:<22}  MISSING (ndpi={bool(ndpi)}, ndpa={os.path.exists(ndpa)})")
            continue
        for sc in STUDY_SCALES:
            # negatives are NOT generated here — they are held constant across
            # conditions (they come from the ratified screened set).
            p, _ = extract_slide_scale(ndpi, ndpa, sid, sc, CONTAM, 0, False)
            print(f"{sid:<22}{sc:>6}{p:>6}", flush=True)
            total += p

    print("-" * 50)
    print(f"TOTAL fabricated positive tiles: {total}  ({(time.time()-t0)/60:.1f} min)")
    print(f"-> {CONTAM}")


if __name__ == "__main__":
    main()
