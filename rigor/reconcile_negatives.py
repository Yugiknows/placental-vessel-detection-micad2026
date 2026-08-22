"""
reconcile_negatives.py — make negatives exactly 1:1 with the SURVIVING positives.

Run this LAST, after the labelImg review of both positives and negatives is
finished. It is a trim-only pass: it deletes surplus negative tiles so that each
(slide, scale) has exactly as many negatives as it has positives left on disk.

Why a separate final pass: the positive count is a moving target while review is
in progress. regen_negatives.py sampled 1:1 against the positives that existed at
the time, but tiles were still being deleted in labelImg mid-run (S.2723_26_BFD_1
went 220 -> 127 while it ran), leaving some slides with a surplus. Reconciling
once at the end is deterministic; reconciling during review is not.

SAFETY: this NEVER touches positives, and never CREATES negatives — it only
removes surplus ones. If a slide is short of 1:1 (some slides genuinely run out
of vessel-free tissue), it is reported, not padded.

    python reconcile_negatives.py --dry-run
    python reconcile_negatives.py
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tiling_config as TC
from slide_registry import load_clean_slides

CORPUS = r"C:\placenta_ssd\tiles_v3"


def tiles_of(corpus, scale, split, sid):
    d = os.path.join(corpus, f"training_data_{scale}", split, "images")
    if not os.path.isdir(d):
        return []
    pre = f"{sid}_{scale}_"
    return sorted(f for f in os.listdir(d)
                  if f.startswith(pre) and f.endswith(".png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    slides = load_clean_slides()
    total_p = total_n = removed = short = 0

    print(f"{'scale':<6}{'slide':<24}{'pos':>6}{'neg':>6}{'action':>22}")
    print("-" * 64)
    for sc in TC.ALL_SCALES:
        for sid in slides:
            pos = tiles_of(args.corpus, sc, "positives", sid)
            neg = tiles_of(args.corpus, sc, "negatives", sid)
            want = len(pos)
            act = "ok (1:1)"
            if len(neg) > want:
                surplus = len(neg) - want
                rng = random.Random(f"{sid}|{sc}|{args.seed}|trim")
                drop = rng.sample(neg, surplus)
                act = f"trim {surplus}"
                if not args.dry_run:
                    ni = os.path.join(args.corpus, f"training_data_{sc}",
                                      "negatives", "images")
                    nl = os.path.join(args.corpus, f"training_data_{sc}",
                                      "negatives", "labels")
                    for f in drop:
                        os.remove(os.path.join(ni, f))
                        t = os.path.join(nl, os.path.splitext(f)[0] + ".txt")
                        if os.path.exists(t):
                            os.remove(t)
                removed += surplus
            elif len(neg) < want:
                act = f"SHORT by {want - len(neg)}"
                short += want - len(neg)
            if pos or neg:
                print(f"{sc:<6}{sid:<24}{len(pos):>6}{len(neg):>6}{act:>22}")
            total_p += len(pos)
            total_n += min(len(neg), want) if len(neg) >= want else len(neg)

    print("-" * 64)
    print(f"{'TOTAL':<30}{total_p:>6}{total_n:>6}")
    print(f"\n{'would remove' if args.dry_run else 'removed'} {removed} surplus negatives")
    if short:
        print(f"{short} negatives SHORT of 1:1 — those slides ran out of "
              f"vessel-free tissue; not padded (would mean duplicating tiles).")

    print("\nfinal counts per zoom:")
    for sc in TC.ALL_SCALES:
        p = sum(len(tiles_of(args.corpus, sc, "positives", s)) for s in slides)
        n = sum(len(tiles_of(args.corpus, sc, "negatives", s)) for s in slides)
        print(f"  {sc:<4} positives={p:<6} negatives={n}")


if __name__ == "__main__":
    main()
