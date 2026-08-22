"""
contamination_audit.py — decide whether an .ndpa is pathologist ground truth
or our own model output, and FAIL CLOSED when it cannot tell.

Why this exists (three defects in prepare_5x_tiles.py::_is_contaminated):

  1. It requires EVERY annotation to carry a <predict> tag
     (`contaminated == len(states)`). A file with 1968 model-generated boxes
     and zero <predict> tags therefore reads as CLEAN. That file is real and
     sitting in this repo:
         runs/predict/multiscale_out/A2FD 1 S.2058 26.ndpi.ndpa
         -> 1968 annotations, 0 <predict> tags, titles "blood_vessel_40x"
     A single genuine pathologist box mixed into a generated file is also
     enough to defeat the all-or-nothing test.

  2. It returns False (== clean) on ET.ParseError.
  3. It returns False (== clean) when the file has zero annotations.

  Both 2 and 3 fail OPEN: an unreadable file is treated as trustworthy.

This module treats any of the following as evidence of machine authorship, and
treats "cannot parse" / "no annotations" as UNKNOWN, never as clean:

  * a <predict> tag on any annotation
  * a title carrying a scale marker, e.g. "blood_vessel_40x" or
    "blood_vessel 99 (40x)" — run_inference.py's naming, never a human's
  * a title beginning with our class name, "blood_vessel"

Verdicts: CLEAN | GENERATED | UNKNOWN. Only CLEAN is admissible, and only a
human may promote a slide into slides_clean.yaml on the strength of it.
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET

# "blood_vessel_40x", "blood_vessel 99 (40x)", "..._5x"
SCALE_IN_TITLE = re.compile(r"(?:_|\()\s*\d+\s*x\s*\)?\s*$|_\d+x\b", re.I)
CLASS_IN_TITLE = re.compile(r"^\s*blood_vessel", re.I)

CLEAN, GENERATED, UNKNOWN = "CLEAN", "GENERATED", "UNKNOWN"


def audit_ndpa(path):
    """Return (verdict, detail_dict). Fails closed to UNKNOWN."""
    detail = {
        "path": path,
        "n_annotations": 0,
        "n_predict_tag": 0,
        "n_scale_title": 0,
        "n_class_title": 0,
        "error": None,
    }

    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        detail["error"] = f"{type(exc).__name__}: {exc}"
        return UNKNOWN, detail

    states = root.findall(".//ndpviewstate")
    detail["n_annotations"] = len(states)
    if not states:
        detail["error"] = "no <ndpviewstate> annotations found"
        return UNKNOWN, detail

    for st in states:
        pred = st.find("predict")
        if pred is not None:
            detail["n_predict_tag"] += 1

        title_el = st.find("title")
        title = (title_el.text or "") if title_el is not None else ""
        if SCALE_IN_TITLE.search(title):
            detail["n_scale_title"] += 1
        if CLASS_IN_TITLE.match(title):
            detail["n_class_title"] += 1

    generated = (
        detail["n_predict_tag"]
        or detail["n_scale_title"]
        or detail["n_class_title"]
    )
    return (GENERATED if generated else CLEAN), detail


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", help="directories to scan for .ndpa")
    args = ap.parse_args()

    found = []
    for root in args.roots:
        for dirpath, _, files in os.walk(root):
            for f in files:
                # skip macOS AppleDouble sidecars from the migration
                if f.startswith("._") or not f.lower().endswith(".ndpa"):
                    continue
                found.append(os.path.join(dirpath, f))

    if not found:
        print("no .ndpa files found under: " + ", ".join(args.roots))
        return 0

    tally = {CLEAN: 0, GENERATED: 0, UNKNOWN: 0}
    print(f"{'verdict':<10} {'annots':>7} {'pred':>5} {'scale':>6} {'class':>6}  path")
    print("-" * 100)
    for path in sorted(found):
        verdict, d = audit_ndpa(path)
        tally[verdict] += 1
        rel = os.path.relpath(path)
        print(f"{verdict:<10} {d['n_annotations']:>7} {d['n_predict_tag']:>5} "
              f"{d['n_scale_title']:>6} {d['n_class_title']:>6}  {rel}")
        if d["error"]:
            print(f"{'':<10} └─ {d['error']}")

    print("-" * 100)
    print(f"CLEAN={tally[CLEAN]}  GENERATED={tally[GENERATED]}  UNKNOWN={tally[UNKNOWN]}")
    print(
        "\nNote: a CLEAN verdict means 'no machine-authorship signature found in\n"
        "this file'. It is necessary, not sufficient, for admitting a slide.\n"
        "Only a human may edit rigor/slides_clean.yaml."
    )
    # non-zero exit if anything is not clean, so this can gate a pipeline
    return 1 if (tally[GENERATED] or tally[UNKNOWN]) else 0


if __name__ == "__main__":
    sys.exit(main())
