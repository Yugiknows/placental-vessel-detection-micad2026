"""
launch_detached.py — start the ablation suite so it SURVIVES session teardown.

WHY THIS EXISTS
Two launch methods already died mid-training:

  1. `nohup python ... &` from the shell    -> killed on session teardown
  2. PowerShell Start-Process with redirect -> killed on session teardown, with:

         forrtl: error (200): program aborting due to window-CLOSE event

That message is the giveaway. It is the Intel Fortran runtime (pulled in by
NumPy/MKL). When the console that owns the process closes, Windows sends
CTRL_CLOSE_EVENT to every process attached to that console, and MKL *aborts*
rather than ignoring it. The training itself was perfectly healthy — loss falling,
2.7 it/s — it was executed by the console dying.

THE FIX
Spawn with DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP so the child owns no
console and belongs to no console process group. It therefore never receives
CTRL_CLOSE_EVENT. (This is the same mechanism that keeps labelImg alive.)
The child writes its own log file, so no parent-owned pipe handles either.

    python launch_detached.py
"""

import os
import subprocess
import sys
import time

RIGOR = os.path.dirname(os.path.abspath(__file__))
LOG = r"C:\placenta_ssd\ablations_detached.log"


def main():
    # DETACHED_PROCESS: no console at all -> no CTRL_CLOSE_EVENT can reach it.
    # CREATE_NEW_PROCESS_GROUP: not in our console's process group either.
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    log = open(LOG, "w", buffering=1, encoding="utf-8", errors="replace")
    p = subprocess.Popen(
        [sys.executable, "-u", os.path.join(RIGOR, "run_ablations.py"), "--run-all"],
        cwd=RIGOR,
        stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    print(f"launched DETACHED — pid {p.pid}")
    print(f"log: {LOG}")

    time.sleep(20)
    if p.poll() is None:
        print("alive after 20s")
    else:
        print(f"*** DIED IMMEDIATELY (exit {p.returncode}) — check the log")
    print("\nThis process now owns no console, so a session teardown cannot "
          "send it CTRL_CLOSE_EVENT.")


if __name__ == "__main__":
    main()
