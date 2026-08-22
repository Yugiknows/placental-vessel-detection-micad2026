"""
supervisor.py — keep the ablation suite running to completion, unattended.

WHY THIS EXISTS
Three things have already interrupted training:
  1. all-runs-in-one-process  -> CUDA OOM on run 2 (PyTorch does not release VRAM
                                 between successive Ultralytics trainings)
  2. `nohup ... &`            -> killed on session teardown
  3. PowerShell Start-Process -> killed by CTRL_CLOSE_EVENT
                                 (`forrtl: error (200): window-CLOSE event` — MKL
                                 aborts instead of ignoring it)
and `A_contam_fabval` was added to the plan *after* the trainer had already started,
so the in-flight process's queue does not contain it.

This supervisor closes all of that:
  * relaunches the runner whenever no trainer is alive and work remains
    (the runner itself skips runs that already have metrics_final.json, so nothing
     is ever retrained or silently recomputed)
  * appends every completed result to RESEARCH_LOG.md as it lands
  * runs DETACHED, so no console close can kill it

    python supervisor.py        # launches itself detached and returns
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

RIGOR = os.path.dirname(os.path.abspath(__file__))
HANDOFF = os.path.join(os.path.dirname(RIGOR), "handoff")
RUNS = os.path.join(HANDOFF, "runs")
LOG = os.path.join(HANDOFF, "RESEARCH_LOG.md")
SUP_LOG = r"C:\placenta_ssd\supervisor.log"

ALL_RUNS = ["baseline", "A_contam_matched", "A_contam_asitwas", "A_contam_fabval",
            "B_sliding_window", "C_blind_negatives", "pilot_mosaic1"]


def done_runs():
    return {r for r in ALL_RUNS
            if os.path.exists(os.path.join(RUNS, r, "metrics_final.json"))}


def trainer_alive():
    """Any python process running run_ablations.py?"""
    try:
        out = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=20).stdout
        return "run_ablations.py" in out
    except Exception:
        # fall back: any python at all
        try:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"],
                                 capture_output=True, text=True, timeout=20).stdout
            return "python.exe" in out
        except Exception:
            return False


def append_note(run):
    """Append a completed run's numbers to the research log."""
    mf = os.path.join(RUNS, run, "metrics_final.json")
    try:
        m = json.load(open(mf))
    except Exception:
        return
    lines = [
        f"\n### AUTO — `{run}` completed ({datetime.now():%Y-%m-%d %H:%M})",
        "",
        f"| metric | value |",
        f"|---|---|",
        f"| mAP50 | **{m['mAP50']:.3f}** (ep {m['mAP50_at_epoch']}) |",
        f"| mAP50-95 | {m['mAP50_95']:.3f} (ep {m['mAP50_95_at_epoch']}) |",
        f"| precision | {m['precision_at_best_mAP50']:.3f} |",
        f"| recall | {m['recall_at_best_mAP50']:.3f} |",
        f"| epochs run | {m['epochs_run']} |",
        f"| s/epoch | {m['seconds_per_epoch']:.0f} |",
        "",
    ]
    fv = m.get("fabricated_val")
    if fv:
        lines += [
            f"**Same model, scored on its OWN FABRICATED validation** "
            f"(`{fv['eval_slide']}`, {fv['eval_tiles']} machine-labelled tiles, "
            f"held OUT of training):",
            "",
            f"| | honest (`BFD_1`) | fabricated (`{fv['eval_slide']}`) |",
            f"|---|---|---|",
            f"| mAP50 | {m['mAP50']:.3f} | **{fv['mAP50']:.3f}** |",
            f"| mAP50-95 | {m['mAP50_95']:.3f} | {fv['mAP50_95']:.3f} |",
            f"| recall | {m['recall_at_best_mAP50']:.3f} | {fv['recall']:.3f} |",
            "",
            "> The fabricated column is the INFLATED score — a model graded against "
            "another model's invented boxes. It is the controlled reproduction of the "
            "0.705/0.780 leak and is **not** a valid measure of detection quality.",
            "",
        ]
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def supervise():
    seen = done_runs()
    for r in seen:
        pass  # already logged by hand or a previous pass
    idle = 0
    while True:
        d = done_runs()
        new = d - seen
        for r in sorted(new):
            append_note(r)
            print(f"[{datetime.now():%H:%M}] logged {r}", flush=True)
        seen |= new

        if len(d) >= len(ALL_RUNS):
            print(f"[{datetime.now():%H:%M}] ALL {len(ALL_RUNS)} RUNS COMPLETE",
                  flush=True)
            with open(LOG, "a", encoding="utf-8") as fh:
                fh.write(f"\n### AUTO — all {len(ALL_RUNS)} runs complete "
                         f"({datetime.now():%Y-%m-%d %H:%M})\n")
            return

        if not trainer_alive():
            idle += 1
            if idle >= 2:      # two consecutive checks with no trainer -> relaunch
                remaining = [r for r in ALL_RUNS if r not in d]
                print(f"[{datetime.now():%H:%M}] no trainer alive; "
                      f"{len(remaining)} runs remain -> relaunching", flush=True)
                subprocess.Popen(
                    [sys.executable, "-u",
                     os.path.join(RIGOR, "run_ablations.py"), "--run-all"],
                    cwd=RIGOR,
                    stdout=open(r"C:\placenta_ssd\ablations_detached.log", "a",
                                buffering=1, encoding="utf-8", errors="replace"),
                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    creationflags=(subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NEW_PROCESS_GROUP),
                    close_fds=True)
                idle = 0
                time.sleep(120)
        else:
            idle = 0
        time.sleep(60)


if __name__ == "__main__":
    if "--worker" in sys.argv:
        supervise()
    else:
        # relaunch self, detached from any console (MKL aborts on CTRL_CLOSE_EVENT)
        p = subprocess.Popen(
            [sys.executable, "-u", os.path.abspath(__file__), "--worker"],
            cwd=RIGOR,
            stdout=open(SUP_LOG, "w", buffering=1, encoding="utf-8", errors="replace"),
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            creationflags=(subprocess.DETACHED_PROCESS
                           | subprocess.CREATE_NEW_PROCESS_GROUP),
            close_fds=True)
        print(f"supervisor running DETACHED (pid {p.pid})")
        print(f"log: {SUP_LOG}")
        print(f"it will: chain all {len(ALL_RUNS)} runs, relaunch on any crash, "
              f"and append each result to RESEARCH_LOG.md")
