"""
status.py — one command, the whole truth. Reads from disk, never from memory.

    python status.py

Shows: which runs are complete / running / queued, the live GPU + orchestrator
state, whether anything is dead, and whether two orchestrators are racing (that
silently corrupted a run once).
"""

import json
import os
import subprocess
import sys

RIGOR = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(os.path.dirname(RIGOR), "handoff", "runs")

ORDER = [
    ("baseline",          "clean reference (= A_clean / B_vessel / C_screened / pilot mosaic0)"),
    ("A_contam_matched",  "CAUSAL fabrication 8.6% — only 459 tiles' labels swapped"),
    ("A_contam_asitwas",  "pre-audit corpus 24% fabricated (confounded: +3 slides)"),
    ("A_contam_fabval",   "clean-trained -> fabricated eval (fictional-labels test)"),
    ("B_sliding_window",  "old sliding-window tiling"),
    ("C_blind_negatives", "unscreened negatives, COUNT-MATCHED (quality only)"),
    ("pilot_mosaic1",     "epoch cap — the SLOW arm (cap must come from mosaic=1)"),
    ("A_contam_heavy",    "fabrication-TRAINED -> held-out fabricated eval (inflation test)"),
]


def sh(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=20, shell=True).stdout
    except Exception:
        return ""


def main():
    gpu = sh("nvidia-smi --query-gpu=utilization.gpu,memory.used "
             "--format=csv,noheader").strip()
    cmds = sh('wmic process where "name=\'python.exe\'" get commandline')
    orch = cmds.count("--run-all")

    done = running = queued = 0
    print("=" * 78)
    print(f"{'#':<3}{'run':<20}{'state':<10}{'mAP50':>7}{'R':>7}{'ep':>5}  detail")
    print("=" * 78)
    for i, (name, what) in enumerate(ORDER, 1):
        d = os.path.join(RUNS, name)
        mf = os.path.join(d, "metrics_final.json")
        csv = os.path.join(d, "results.csv")
        if os.path.exists(mf):
            m = json.load(open(mf))
            done += 1
            extra = ""
            fv = m.get("fabricated_val")
            if fv:
                extra = f" | FAB-VAL mAP50={fv['mAP50']:.3f}"
            print(f"{i:<3}{name:<20}{'DONE':<10}{m['mAP50']:>7.3f}"
                  f"{m['recall_at_best_mAP50']:>7.3f}{m['epochs_run']:>5}{extra}")
        elif os.path.exists(csv):
            e = sum(1 for _ in open(csv)) - 1
            running += 1
            print(f"{i:<3}{name:<20}{'RUNNING':<10}{'':>7}{'':>7}{e:>5}  <-- in flight")
        else:
            queued += 1
            print(f"{i:<3}{name:<20}{'queued':<10}")
    print("=" * 78)
    print(f"  {done} complete · {running} running · {queued} queued")
    print()
    print(f"  GPU            : {gpu}")
    print(f"  orchestrators  : {orch}", end="")
    if orch == 0 and running:
        print("   *** DEAD — a run is unfinished but nothing is training. RESTART. ***")
    elif orch > 1:
        print("   *** TWO RUNNERS — race risk, they will clobber the same dir. KILL ONE. ***")
    elif orch == 0 and queued:
        print("   *** DEAD — runs remain queued but nothing is training. RESTART. ***")
    else:
        print("   (ok)")

    lock = os.path.join(RUNS, ".runner.lock")
    if os.path.exists(lock):
        pid = open(lock).read().strip()
        alive = pid in sh(f"tasklist /FI \"PID eq {pid}\"")
        print(f"  lock           : pid {pid} {'(alive)' if alive else '(STALE — clear it)'}")

    print("\n  restart:  python launch_detached.py     (clears nothing — do that first)")
    print("  a killed PARTIAL must be deleted before re-running; a COMPLETE run is "
          "skipped forever.")


if __name__ == "__main__":
    main()
