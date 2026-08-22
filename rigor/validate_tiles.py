"""
validate_tiles.py — prove the tiles actually frame the vessel.

The user's complaint ("they don't have the proper bloodvessel on the tiles") is
measurable, so we measure it rather than assert it. For every positive tile we
look at its PRIMARY box (the largest one — the vessel the tile is supposed to be
about) and check:

  edge_clipped   box touches the tile border  -> vessel is cut in half
  vessel_tiny    box < 1% of tile area        -> vessel is a speck, no framing
  off_centre     box centre far from the tile centre
  vessel_area    median box area as % of tile -> the vessel-to-frame ratio that
                 the whole per-magnification decomposition depends on

Run it against any tile root to compare methods head-to-head.

    python validate_tiles.py --root C:\placenta_ssd\tiles_v3
    python validate_tiles.py --compare
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tiling_config as TC

EDGE_TOL = 0.005          # within 0.5% of the border counts as touching


def scan(root, scale, positives_sub=None):
    """-> dict of framing stats over the positive tiles of one scale."""
    cands = [positives_sub] if positives_sub else [
        os.path.join(f"training_data_{scale}", "positives", "labels"),
        os.path.join(f"training_data_{scale}", "train", "positives", "labels"),
    ]
    lbl_dir = next((os.path.join(root, c) for c in cands
                    if os.path.isdir(os.path.join(root, c))), None)
    if not lbl_dir:
        return None

    n = edge = tiny = 0
    areas = []
    offs = []
    for f in os.listdir(lbl_dir):
        # skip macOS AppleDouble sidecars (binary junk) left by the Mac migration
        if f.startswith("._") or not f.endswith(".txt") or f == "classes.txt":
            continue
        try:
            raw = open(os.path.join(lbl_dir, f)).read()
        except (UnicodeDecodeError, OSError):
            continue
        rows = [r.split() for r in raw.split("\n") if r.strip()]
        rows = [r for r in rows if len(r) >= 5 and r[0].lstrip("-").isdigit()]
        if not rows:
            continue
        n += 1
        # primary = biggest box on the tile
        cx, cy, w, h = max(((float(r[1]), float(r[2]), float(r[3]), float(r[4]))
                            for r in rows), key=lambda b: b[2] * b[3])
        areas.append(w * h)
        offs.append(max(abs(cx - 0.5), abs(cy - 0.5)))
        if (cx - w / 2 <= EDGE_TOL or cy - h / 2 <= EDGE_TOL
                or cx + w / 2 >= 1 - EDGE_TOL or cy + h / 2 >= 1 - EDGE_TOL):
            edge += 1
        if w * h < 0.01:
            tiny += 1

    if not n:
        return None
    areas.sort()
    offs.sort()
    return {
        "tiles": n,
        "edge_pct": 100.0 * edge / n,
        "tiny_pct": 100.0 * tiny / n,
        "median_area_pct": 100.0 * areas[len(areas) // 2],
        "median_offcentre": offs[len(offs) // 2],
    }


def report(root, label):
    print(f"\n=== {label}\n    {root}")
    print(f"{'scale':<6}{'tiles':>7}{'vessel ON EDGE':>16}{'vessel <1% frame':>18}"
          f"{'median vessel':>15}{'off-centre':>12}")
    print("-" * 74)
    ok = True
    for sc in TC.ALL_SCALES:
        s = scan(root, sc)
        if not s:
            print(f"{sc:<6}{'--':>7}")
            continue
        flag = ""
        if s["edge_pct"] > 25:
            flag = "  <-- BAD"
            ok = False
        print(f"{sc:<6}{s['tiles']:>7}{s['edge_pct']:>15.1f}%{s['tiny_pct']:>17.1f}%"
              f"{s['median_area_pct']:>14.1f}%{s['median_offcentre']:>12.2f}{flag}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"C:\placenta_ssd\tiles_v3")
    ap.add_argument("--compare", action="store_true",
                    help="compare v3 against the old grid tiling + the hand corpus")
    args = ap.parse_args()

    if not args.compare:
        ok = report(args.root, "tiles")
        print("\nVERDICT:", "framing OK" if ok else "*** FRAMING STILL BAD ***")
        return

    report(r"C:\placenta_ssd\training_clean",
           "OLD: whole-slide sliding window (the bad one)")
    report(r"D:\windows_gpu_migration\placenta_training",
           "REFERENCE: original hand-curated corpus")
    ok = report(args.root, "NEW: vessel-centred v3 (the fix)")
    print("\nLower `vessel ON EDGE` = the vessel is whole and framed, not cut by "
          "the tile border.")
    print("VERDICT:", "FIXED" if ok else "*** STILL BAD ***")


if __name__ == "__main__":
    main()
