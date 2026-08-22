"""
stage_to_ssd.py — move the tiling working set onto the NVMe SSD.

ROOT CAUSE of the slow tiling: D: is a WDC WD10EZEX 7200rpm HDD; C: is a
WD_BLACK SN850X NVMe SSD. Whole-slide tiling issues ~20k small RANDOM reads per
slide (one per grid cell for the tissue check). An HDD serves ~100 random IOPS;
the NVMe serves >100k. Worse, running 8 workers against an HDD makes it *slower*
— the head thrashes between streams (we measured 344% disk-busy at 8% CPU).

This copies ONLY the audited-CLEAN slide+annotation pairs to the SSD, which also
means a contaminated .ndpa physically cannot come along.

Staging the tiles on SSD pays off twice: tiling now, and YOLO training later
(the dataloader re-reads every tile every epoch).
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from annotation_scale_report import discover_clean_sources
from retile_clean import DEFAULT_SLIDES

SSD_ROOT = r"C:\placenta_ssd"
SSD_SLIDES = os.path.join(SSD_ROOT, "slides")


def human(n):
    return f"{n/1024/1024/1024:.1f} GB"


def main():
    os.makedirs(SSD_SLIDES, exist_ok=True)
    sources = discover_clean_sources()

    copied = skipped = 0
    total = 0
    for sid in DEFAULT_SLIDES:
        if sid not in sources or sources[sid][1] is None:
            print(f"  !! no clean source for {sid} — skipped")
            continue
        ndpa, ndpi, n = sources[sid]
        for src in (ndpi, ndpa):
            dst = os.path.join(SSD_SLIDES, os.path.basename(src))
            if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
                skipped += 1
                continue
            sz = os.path.getsize(src)
            print(f"  copying {os.path.basename(src)} ({human(sz)}) ...", flush=True)
            shutil.copy2(src, dst)
            total += sz
            copied += 1

    print(f"\ncopied {copied} files ({human(total)}), {skipped} already present")
    print(f"SSD slide root: {SSD_SLIDES}")


if __name__ == "__main__":
    main()
