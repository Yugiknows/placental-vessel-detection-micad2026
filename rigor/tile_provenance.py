"""
tile_provenance.py — a per-tile verification ledger (refines constraint C2).

The slide allow-list (slides_clean.yaml) is per-SLIDE, but contamination is
per-ANNOTATION: a tile a human drew/checked in labelImg is trustworthy even if
that slide's source .ndpa was later overwritten by model output. Conversely, a
tile auto-extracted from a corrupt .ndpa is untrustworthy even on a slide we
otherwise like. This ledger records the verification state of every individual
tile so that:

  * manually-verified tiles are never silently dropped or overwritten, and
  * hand-fixed tiles on otherwise-corrupt slides can be re-admitted, while
  * auto-extracted tiles on corrupt slides are held out until a human rules.

`scan`   builds/refreshes tiles_ledger.csv, one row per tile, defaulting each
         tile's `verified` from allow-list membership but never overwriting a
         human's edit.
`build`  materialises a training corpus containing ONLY rows with
         verified == yes, and stamps the tile-set into a manifest.

Nothing here parses WSIs or runs a model — it only reads existing tile files,
so it works on this machine as-is.
"""

import argparse
import csv
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
from slide_registry import SCALES, load_raw
from tiling_fingerprint import slide_of

DATA_ROOT = paths.PLACENTA_TRAINING
LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiles_ledger.csv")

# Verification states.
YES, NO, UNKNOWN = "yes", "no", "unknown"

FIELDS = [
    "tile_id", "slide", "scale", "kind", "n_boxes",
    "label_sha", "img_bytes", "verified", "source", "note",
]


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def _kind(dirpath):
    n = dirpath.replace("\\", "/")
    if "/negatives" in n:
        return "neg"
    if "/val" in n:
        return "val_pos"
    if "/test" in n:
        return "test_pos"
    if "/positives" in n:
        return "pos"
    return None


def _default_verified(slide, kind, include, exclude):
    """Conservative default; a human edit in the CSV always wins over this."""
    if slide in include:
        return YES if kind != "neg" else YES  # clean-slide tiles trusted
    if slide in exclude:
        return UNKNOWN                          # corrupt slide -> human must rule
    return UNKNOWN                              # slide not in either list yet


def scan(data_root=DATA_ROOT, ledger_path=LEDGER):
    doc = load_raw()
    include = set(doc.get("include") or [])
    exclude = set((doc.get("exclude") or {}).keys())

    # Preserve any human edits already in the ledger.
    prior = {}
    if os.path.exists(ledger_path):
        with open(ledger_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                prior[row["tile_id"]] = row

    rows = []
    for scale in SCALES + ("5x",):
        root = os.path.join(data_root, f"training_data_{scale}")
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            kind = _kind(dirpath)
            if kind is None or "labels" not in dirpath.replace("\\", "/"):
                continue
            for f in sorted(files):
                if f.startswith("._") or f == "classes.txt" or not f.endswith(".txt"):
                    continue
                slide = slide_of(f, scale)
                if slide is None:
                    continue
                lbl = os.path.join(dirpath, f)
                img = _find_image(lbl)
                tile_id = f"{scale}/{os.path.splitext(f)[0]}"

                with open(lbl, encoding="utf-8") as lf:
                    n_boxes = sum(1 for ln in lf if ln.strip())

                if tile_id in prior:               # keep human decision
                    verified = prior[tile_id]["verified"]
                    source = prior[tile_id].get("source", "")
                    note = prior[tile_id].get("note", "")
                else:
                    verified = _default_verified(slide, kind, include, exclude)
                    source = "allowlist_default"
                    note = ""

                rows.append({
                    "tile_id": tile_id,
                    "slide": slide,
                    "scale": scale,
                    "kind": kind,
                    "n_boxes": n_boxes,
                    "label_sha": _sha(lbl),
                    "img_bytes": os.path.getsize(img) if img else 0,
                    "verified": verified,
                    "source": source,
                    "note": note,
                })

    rows.sort(key=lambda r: r["tile_id"])
    with open(ledger_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    summarise(rows)
    print(f"\nwrote {ledger_path} ({len(rows)} tiles)")
    print("Edit the `verified` column (yes/no/unknown) then rerun `build`.")
    return rows


def _find_image(label_path):
    base = label_path.replace("\\", "/")
    stem = os.path.splitext(base)[0].replace("/labels/", "/images/")
    for ext in (".png", ".jpg", ".jpeg"):
        if os.path.exists(stem + ext):
            return stem + ext
    return None


def summarise(rows):
    from collections import Counter
    print(f"{'scale':<6} {'slide':<24} {'yes':>5} {'unknown':>8} {'no':>4}")
    print("-" * 50)
    agg = Counter()
    for r in rows:
        agg[(r["scale"], r["slide"], r["verified"])] += 1
    slides = sorted({(r["scale"], r["slide"]) for r in rows})
    for scale, slide in slides:
        y = agg[(scale, slide, YES)]
        u = agg[(scale, slide, UNKNOWN)]
        n = agg[(scale, slide, NO)]
        flag = "  <- has UNKNOWN, needs a ruling" if u else ""
        print(f"{scale:<6} {slide:<24} {y:>5} {u:>8} {n:>4}{flag}")


def build(data_root=DATA_ROOT, ledger_path=LEDGER, out_dir=None):
    if not os.path.exists(ledger_path):
        sys.exit("no ledger yet — run `scan` first.")
    with open(ledger_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    unknown = [r for r in rows if r["verified"] == UNKNOWN]
    if unknown:
        by_slide = {}
        for r in unknown:
            by_slide.setdefault((r["scale"], r["slide"]), 0)
            by_slide[(r["scale"], r["slide"])] += 1
        print("REFUSING to build: tiles still marked `unknown`:")
        for (sc, sl), c in sorted(by_slide.items()):
            print(f"  {sc} {sl}: {c}")
        print("\nResolve every `unknown` to yes or no in the ledger first.")
        sys.exit(2)

    kept = [r for r in rows if r["verified"] == YES]
    manifest = {
        "n_tiles": len(kept),
        "tiles": sorted(r["tile_id"] for r in kept),
        "ledger_sha": _sha(ledger_path),
    }
    out_dir = out_dir or os.path.join(os.path.dirname(ledger_path), "verified_corpus")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "verified_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"verified corpus: {len(kept)} tiles -> {out_dir}/verified_manifest.json")
    print("(this manifest is the tile-set of record; the runner consumes it, "
          "not a raw glob.)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="build/refresh the per-tile ledger")
    sub.add_parser("build", help="materialise the verified-only corpus manifest")
    args = ap.parse_args()
    if args.cmd == "scan":
        scan()
    else:
        build()
