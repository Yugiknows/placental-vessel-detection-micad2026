"""
tiling_config.py — the single source of truth for tiling parameters (feeds 4.2).

Everything here is hashed into the tiling fingerprint stamped on every run.
Changing any value here invalidates prior runs (constraint C3).

WHY THESE VALUES (each fixes a measured defect):

METHOD = vessel-centered, NOT whole-slide sliding window.
    The sliding-window tiler (prepare_training_tiles.py) put the vessel box on a
    tile EDGE in 58% of positive tiles, vs 18% for vessel-centered — measured over
    the real corpus. It is the same approach that produced the directory the user
    named `training_data_10x_v2_wholeslide_flawed_...`. A sliding grid cannot
    give "tiles where the vessel-to-frame size ratio is roughly consistent",
    which is the premise the whole per-magnification experiment rests on.
    Vessel-centered crops put the triggering vessel whole and centred, every time.

SNUG_FRAC = 0.8
    A vessel is only assigned to a scale if it fits within 80% of that scale's
    tile, leaving real context around it. This closes a silent bug: 10x had
    max_l0_px=None ("catch-all for big vessels") but a 10x tile only spans
    4096 level-0 px, so 30 real vessels were too big to frame and were clipped
    or dropped. Capping 10x at the snug limit sends those to 5x instead.

MIN_VISIBLE_FRAC = 0.35
    For OTHER vessels that happen to fall in a tile: label them only if at least
    this much of their area is inside. The old grid tiler used 0.10, so a tile
    counted as positive when a mere 10% sliver of a vessel touched its edge, and
    the label was drawn around the sliver — training the detector that a fragment
    of a vessel wall IS a vessel. The primary (centred) vessel is always fully
    visible by construction, so this only governs incidental neighbours.
"""

TILE_SIZE = 1024          # px, the model's input tile (imgsz=1024)
SNUG_FRAC = 0.80          # vessel must fit inside this fraction of the tile
MIN_VISIBLE_FRAC = 0.35   # min visible area fraction to label a NEIGHBOUR vessel
MIN_BOX_PX = 8            # drop degenerate slivers below this many tile px
WHITE_THRESH = 220        # mean RGB above this = background glass, not tissue
# Negatives: tissue tiles with NO vessel of any size.
# 1:1 with positives, per user instruction — the negative count in each zoom
# matches that zoom's positive count. Counted against the positives that ACTUALLY
# EXIST ON DISK after the user's labelImg review (they deleted some tiles), not
# against what the tiler originally emitted.
NEG_RATIO = 1.0           # negatives per positive, per slide per scale
NEG_CAP = 20000           # effectively off; the 1:1 ratio is the real control

# ── Negative screening (NEG_SCREEN_CONF) ─────────────────────────────────────
# The .ndpa annotations are NOT exhaustive: the pathologist annotated a SUBSET of
# vessels, so "no annotation overlaps this tile" does not mean "no vessel is in
# this tile". Measured with the trusted model: 11% of 10x, 15% of 20x, 5% of 40x
# and 9% of 5x sampled negatives actually contained a visible vessel.
#
# An unlabelled vessel inside a NEGATIVE tile is the worst kind of label noise —
# it explicitly teaches the detector that a visible vessel is background,
# suppressing true positives and corrupting the recall numbers the paper's claim
# rests on.
#
# So every candidate negative is screened with the TRUSTED pre-contamination
# model (blood_vessel_best_BACKUP.pt, dated 2026-06-05, before the first
# NDPA-overwrite; it cannot carry fabricated boxes). Any candidate in which it
# detects a vessel at >= this confidence is DISCARDED.
#
# This is screening, NOT labelling: no model output ever becomes a training
# label, so it is not a contamination path. Threshold is deliberately LOW —
# we would rather throw away a good negative than keep one hiding a vessel.
#
# THRESHOLD CALIBRATION (measured, % of KNOWN-POSITIVE tiles the model fires on
# — i.e. its recall, which is what matters for a screener):
#     conf    10x   20x   40x
#     0.30    34%   27%   25%
#     0.20    43%   35%   31%   <- useless as a screener; misses ~2/3 of vessels
#     0.10    56%   47%   39%
#     0.05    64%   54%   49%
#     0.02    78%   68%   65%
#     0.01    89%   78%   88%   <- chosen
# The model has poor recall, so it must be run at a very low confidence to be a
# useful filter. At 0.01 it catches ~80-90% of vessel-bearing tiles. The residual
# is caught by the human labelImg review of the negatives — automated screening
# plus human verification, neither alone.
#
# Caveat to state in the paper: negatives are therefore "tissue in which neither
# a pathologist annotation nor a trusted detector found a vessel", not "uniformly
# sampled tissue".
NEG_SCREEN_CONF = 0.01

# Screening is a UNION of two independent detectors + TTA. One model is not
# enough: the pre-contamination model alone misses ~1 in 10 vessels (78-92%
# recall) and the user could still SEE vessels in tiles it passed. A candidate is
# discarded if EITHER model fires, so a vessel must fool BOTH to survive.
#   1. blood_vessel_best_BACKUP.pt  — trusted, pre-contamination (independent)
#   2. screener/run/weights/best.pt — trained on the CLEAN hand-reviewed
#      positives of THIS corpus, so it knows what these vessels look like
# Used only to REJECT candidates; no model output ever becomes a label.
NEG_SCREEN_MODELS = [
    "blood_vessel_best_BACKUP.pt",
    "screener_best.pt",
]
NEG_SCREEN_TTA = True     # flips/scales at inference — recovers vessels a single
                          # forward pass misses, at the cost of ~3x screening time

# Vessels are continuous, branching structures: the annotation box bounds the
# vessel a pathologist drew, but its branches and lumen continue past that box.
# A tile that merely fails to OVERLAP an annotation can still contain the same
# vessel's continuation. Reject candidates within this margin (as a fraction of
# the tile span) of ANY annotation.
NEG_ANNOT_MARGIN_FRAC = 0.25
CENTRE_SNAP_DIV = 2       # dedup: snap centres to (half_tile / this) grid

# Per-scale: fixed downsample + which vessel sizes (level-0 px) belong here.
# tile_span_l0 = TILE_SIZE * downsample ; snug_max = tile_span_l0 * SNUG_FRAC
#   40x: ds=1  -> span  1024 -> snug  819
#   20x: ds=2  -> span  2048 -> snug 1638
#   10x: ds=4  -> span  4096 -> snug 3277   <- was None (unframeable), now capped
#    5x: ds=16 -> span 16384 -> snug 13107  <- catches what 10x cannot frame
#
# 5x downsample: ds=32 was WRONG and validate_tiles.py caught it — a 32768px tile
# makes a 2400px vessel 0.5% of the frame, and 62% of 5x tiles came out as specks.
# ds=16 frames the same vessels at 15%-80% of the tile. The largest vessel in the
# corpus is 14043 l0px; one vessel exceeds the 13107 snug cap and is dropped.
SCALE_GATES = {
    "40x": {"downsample": 1.0,  "min_l0_px": 15,   "max_l0_px": 450},
    "20x": {"downsample": 2.0,  "min_l0_px": 100,  "max_l0_px": 1200},
    "10x": {"downsample": 4.0,  "min_l0_px": 450,  "max_l0_px": 3277},
    "5x":  {"downsample": 16.0, "min_l0_px": 2400, "max_l0_px": 13100},
}

CORE_SCALES = ("10x", "20x", "40x")   # the three detectors under test
ALL_SCALES = ("10x", "20x", "40x", "5x")

METHOD = "vessel_centered_v3"


def tile_span_l0(scale):
    return TILE_SIZE * SCALE_GATES[scale]["downsample"]


def snug_max_l0(scale):
    return tile_span_l0(scale) * SNUG_FRAC


def as_dict():
    """Exactly what gets hashed into the tiling fingerprint."""
    return {
        "method": METHOD,
        "tile_size": TILE_SIZE,
        "snug_frac": SNUG_FRAC,
        "min_visible_frac": MIN_VISIBLE_FRAC,
        "min_box_px": MIN_BOX_PX,
        "white_thresh": WHITE_THRESH,
        "neg_ratio": NEG_RATIO,
        "neg_cap": NEG_CAP,
        "neg_screen_conf": NEG_SCREEN_CONF,
        "neg_screen_models": NEG_SCREEN_MODELS,
        "neg_screen_tta": NEG_SCREEN_TTA,
        "neg_annot_margin_frac": NEG_ANNOT_MARGIN_FRAC,
        "human_reviewed": True,   # every tile was checked in labelImg by the user
        "centre_snap_div": CENTRE_SNAP_DIV,
        "scale_gates": SCALE_GATES,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(as_dict(), indent=2, sort_keys=True))
    print()
    for sc in ALL_SCALES:
        g = SCALE_GATES[sc]
        print(f"{sc:>4}: ds={g['downsample']:>5}  tile covers {tile_span_l0(sc):>7.0f} l0px  "
              f"gate {g['min_l0_px']}-{g['max_l0_px']}  snug_max={snug_max_l0(sc):.0f}")
