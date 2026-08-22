"""
train_run.py — trainer wrapper for one run of the manifest (4.4).

Sets every seed (python / numpy / torch / cudnn / ultralytics `seed=`), applies
the resolved augmentation, trains, and writes to the run dir:
    resolved_config.json   every hyperparameter actually used
    meta.json              tiling_hash, git commit, seed, host, timings
    results.csv/weights    ultralytics' own outputs

Resumable (C3 + the migration lesson): a run is skipped iff its meta.json exists,
is marked complete, AND its tiling_hash matches the manifest. A run trained on
different tiles is NOT reusable, so a hash mismatch forces a retrain rather than
silently mixing corpora.
"""

import argparse
import json
import os
import platform
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def set_all_seeds(seed):
    import numpy as np
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def git_commit():
    for d in (os.path.dirname(os.path.abspath(__file__)),
              os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        try:
            out = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"],
                                 capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                return out.stdout.strip()
        except Exception:
            pass
    return "no_git_repo"


def is_complete(run, tiling_hash):
    meta = os.path.join(run["out_dir"], "meta.json")
    if not os.path.exists(meta):
        return False
    try:
        with open(meta) as fh:
            m = json.load(fh)
    except json.JSONDecodeError:
        return False
    if not m.get("complete"):
        return False
    if m.get("tiling_hash") != tiling_hash:
        # C3: trained on different tiles -> not reusable
        return False
    return True


def train_one(run, tiling_hash, epochs=None, dry=False):
    from ultralytics import YOLO

    out = run["out_dir"]
    os.makedirs(out, exist_ok=True)
    fixed = dict(run["fixed"])
    if epochs:
        fixed["epochs"] = epochs

    set_all_seeds(run["seed"])

    cfg = dict(
        data=run["data_yaml"],
        epochs=fixed["epochs"],
        imgsz=fixed["imgsz"],
        batch=fixed["batch"],
        patience=fixed["patience"],
        optimizer=fixed["optimizer"],
        device=fixed["device"],
        seed=run["seed"],
        deterministic=True,
        project=os.path.dirname(out),
        name=os.path.basename(out),
        exist_ok=True,
        verbose=False,
        plots=False,
        val=True,
        **run["aug"],
    )

    with open(os.path.join(out, "resolved_config.json"), "w") as fh:
        json.dump(cfg, fh, indent=2)

    if dry:
        print(f"[dry] {run['run_id']}")
        return None

    t0 = time.time()
    model = YOLO(fixed["model"])
    res = model.train(**cfg)
    dt = time.time() - t0

    metrics = {}
    try:
        rd = res.results_dict
        metrics = {k: float(v) for k, v in rd.items()}
    except Exception:
        pass

    meta = {
        "run_id": run["run_id"],
        "complete": True,
        "tiling_hash": tiling_hash,
        "git_commit": git_commit(),
        "seed": run["seed"],
        "arch": run["arch"],
        "scale": run["scale"],
        "fold": run["fold"],
        "mosaic": run["mosaic"],
        "hsv_s": run["hsv_s"],
        "cell": run["cell"],
        "data_yaml": run["data_yaml"],
        "train_seconds": dt,
        "epochs_requested": fixed["epochs"],
        "metrics": metrics,
        "host": platform.node(),
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(os.path.join(out, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "run_manifest.json"))
    ap.add_argument("--run-id", help="train exactly this run")
    ap.add_argument("--epochs", type=int, help="override (timing tests only)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.manifest) as fh:
        man = json.load(fh)
    th = man["tiling_hash"]

    runs = man["runs"]
    if args.run_id:
        runs = [r for r in runs if r["run_id"] == args.run_id]
        if not runs:
            sys.exit(f"no such run_id: {args.run_id}")

    r = runs[0]
    if is_complete(r, th) and not args.epochs:
        print(f"skip (complete, hash matches): {r['run_id']}")
        return
    m = train_one(r, th, args.epochs, args.dry_run)
    if m:
        print(f"done {m['run_id']} in {m['train_seconds']/60:.1f} min")
        print(json.dumps(m["metrics"], indent=2))


if __name__ == "__main__":
    main()
