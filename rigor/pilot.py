"""
pilot.py — measure the epoch budget the real grid needs, WITHOUT biasing it.

THE TRAP THIS EXISTS TO AVOID
Mosaic is a harder, more heavily-regularised training task, so mosaic=1.0 runs
generally converge LATER than mosaic=0.0 runs. If we picked an epoch cap by
watching a mosaic=0 run and applied it to everything, we would cut the mosaic=1
runs off BEFORE they converged. Mosaic would then look worse than it really is —
and "mosaic harms the decomposed detector" is precisely the paper's hypothesis.
We would have manufactured our own result as a training artefact. A reviewer will
ask "did you show the mosaic arms had converged?"; if we cannot, the paper dies.

So the pilot trains BOTH mosaic arms (and both architectures) on one fold with a
generous budget + patience, records where each one actually peaks, and reports:

    cap = max over arms of (best_epoch) + margin

If the mosaic=1 arm is still improving at the cap, the cap is INVALID no matter
how much compute it would save. The script says so explicitly.

    python pilot.py                 # run the 4 pilot cells
    python pilot.py --report        # analyse whatever has finished
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RIGOR = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(RIGOR, "run_manifest.json")
PILOT_FOLD = 0
PILOT_SEED = 0
MARGIN = 1.25          # cap = slowest best_epoch x this


def pilot_run_ids(man):
    """The 4 cells that bracket the question: both arch x both mosaic."""
    want = []
    for r in man["runs"]:
        if r["fold"] != PILOT_FOLD or r["seed"] != PILOT_SEED:
            continue
        if r["hsv_s"] != 0.05:
            continue
        # per_mag_3x is 3 models; take 10x as its representative for the pilot
        if r["arch"] == "per_mag_3x" and r["scale"] != "10x":
            continue
        want.append(r)
    return want


def best_epoch_from_csv(run_dir):
    csv = os.path.join(run_dir, "results.csv")
    if not os.path.exists(csv):
        return None
    rows = [ln.strip().split(",") for ln in open(csv) if ln.strip()]
    hdr = [h.strip() for h in rows[0]]
    try:
        i_map = hdr.index("metrics/mAP50(B)")
    except ValueError:
        return None
    best_e, best_v, last_e = 0, -1.0, 0
    vals = []
    for r in rows[1:]:
        try:
            e = int(float(r[0]))
            v = float(r[i_map])
        except (ValueError, IndexError):
            continue
        vals.append((e, v))
        last_e = e
        if v > best_v:
            best_v, best_e = v, e
    if not vals:
        return None
    # still improving? best in the last 20% of epochs = not plateaued
    tail_start = last_e * 0.8
    still_improving = best_e >= tail_start
    return {"best_epoch": best_e, "best_map50": best_v,
            "last_epoch": last_e, "still_improving": still_improving}


def report(man):
    runs = pilot_run_ids(man)
    print(f"{'arch':<16}{'mosaic':>7}{'best_ep':>9}{'mAP50':>8}"
          f"{'last_ep':>9}  status")
    print("-" * 62)
    results = []
    for r in runs:
        b = best_epoch_from_csv(r["out_dir"])
        if not b:
            print(f"{r['arch']:<16}{r['mosaic']:>7}{'--':>9}  (not run yet)")
            continue
        status = ("STILL IMPROVING — cap would truncate it"
                  if b["still_improving"] else "plateaued")
        print(f"{r['arch']:<16}{r['mosaic']:>7}{b['best_epoch']:>9}"
              f"{b['best_map50']:>8.3f}{b['last_epoch']:>9}  {status}")
        results.append((r, b))

    if not results:
        print("\nnothing to report yet.")
        return

    print("-" * 62)
    truncated = [r for r, b in results if b["still_improving"]]
    slowest = max(results, key=lambda rb: rb[1]["best_epoch"])
    cap = int(slowest[1]["best_epoch"] * MARGIN)

    m0 = [b["best_epoch"] for r, b in results if r["mosaic"] == 0.0]
    m1 = [b["best_epoch"] for r, b in results if r["mosaic"] == 1.0]
    if m0 and m1:
        print(f"\nbest epoch, mosaic=0 arm : {sorted(m0)}")
        print(f"best epoch, mosaic=1 arm : {sorted(m1)}")
        if max(m1) > max(m0):
            print(f"  -> mosaic=1 converges LATER (as expected). A cap chosen "
                  f"from the mosaic=0 arm alone would have truncated it and\n"
                  f"     made mosaic look artificially bad — i.e. faked the "
                  f"paper's own hypothesis.")

    print(f"\nslowest arm: {slowest[0]['arch']} mosaic={slowest[0]['mosaic']} "
          f"peaked at epoch {slowest[1]['best_epoch']}")
    if truncated:
        print("\n*** DO NOT SET A CAP YET ***")
        for r in truncated:
            print(f"    {r['arch']} mosaic={r['mosaic']} was still improving at "
                  f"the end of its run — it never converged.")
        print("    Re-run the pilot with more epochs before choosing a budget.")
    else:
        print(f"\nRECOMMENDED EPOCH CAP: {cap}   "
              f"(slowest best_epoch x {MARGIN}, all arms plateaued)")
        print("Apply this IDENTICALLY to all 12 cells (§3).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--epochs", type=int, default=300)
    args = ap.parse_args()

    with open(MANIFEST) as fh:
        man = json.load(fh)

    if args.report:
        report(man)
        return

    runs = pilot_run_ids(man)
    print(f"pilot: {len(runs)} cells on fold {PILOT_FOLD}, seed {PILOT_SEED}")
    print("both architectures x BOTH mosaic settings — the mosaic=1 arm is the "
          "whole point:\nif it converges later, the cap must accommodate it.\n")
    for r in runs:
        print(f"  {r['arch']:<16} mosaic={r['mosaic']}")
    print()

    for r in runs:
        print(f"\n=== {r['run_id']} ===", flush=True)
        subprocess.run([sys.executable, os.path.join(RIGOR, "train_run.py"),
                        "--run-id", r["run_id"], "--epochs", str(args.epochs)],
                       check=False)
    print("\npilot done — now: python pilot.py --report")


if __name__ == "__main__":
    main()
