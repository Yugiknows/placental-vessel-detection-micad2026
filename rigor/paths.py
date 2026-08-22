"""
paths.py — the machine-specific roots, resolved from the environment.

This module exists only on the `portable` branch. On `main` every path below is a
hard-coded literal inside the module that uses it, exactly as it was when the
published results were produced; `main` is the byte-identical provenance record and
must not be edited. See README.md, "The two branches".

Every root reads an environment variable and falls back to the original Windows
value the study actually ran on. With no environment set, on Windows, the resolved
strings are identical to the literals on `main`, so behaviour there is unchanged.

To run on macOS or Linux, set the roots you need:

    export PLACENTA_SSD_ROOT=/Volumes/Extreme\\ SSD/placenta_ssd
    export PLACENTA_SLIDES_ROOT=/Volumes/Extreme\\ SSD/PLACENTA_SLIDES
    export PLACENTA_BACKUP_ROOT=/Volumes/Extreme\\ SSD/placenta_BACKUP
    export PLACENTA_MIGRATION_ROOT=/Volumes/Extreme\\ SSD/windows_gpu_migration

Values are exported as `str`, not `Path`. The modules that consume them pass them to
os.path.join, os.walk, open and shutil, all of which accept either — but exporting
str keeps every downstream expression behaving exactly as it does on `main`.

Run `python rigor/paths.py` to print the resolved values for the current environment.
"""

import os
from pathlib import Path


def _root(env_name, windows_default):
    """The configured root, or the original Windows path the study ran on."""
    return Path(os.environ.get(env_name, windows_default))


# ── the five configurable roots ──────────────────────────────────────────────
SSD_ROOT       = _root("PLACENTA_SSD_ROOT",       r"C:\placenta_ssd")
SLIDES_DRIVE   = _root("PLACENTA_SLIDES_ROOT",    r"D:\PLACENTA SLIDES")
BACKUP_ROOT    = _root("PLACENTA_BACKUP_ROOT",    r"D:\placenta_BACKUP")
MIGRATION_ROOT = _root("PLACENTA_MIGRATION_ROOT", r"D:\windows_gpu_migration")
# <REPO> in the archived runs/*/args.yaml. No module hard-codes it — tiling_fingerprint
# derives the project dir relatively — but it is the fifth machine-specific root and is
# resolved here so the set is complete.
REPO_ROOT      = _root("PLACENTA_REPO_ROOT",
                       r"D:\windows_gpu_migration\Yolo11_training-yolo11_train_seg_classify_v2")

# ── derived: the tile corpora on the NVMe ────────────────────────────────────
TILES_V3           = str(SSD_ROOT / "tiles_v3")             # the ratified v3 corpus
TRAINING_CLEAN     = str(SSD_ROOT / "training_clean")       # OLD sliding-window tiles
TILES_CONTAMINATED = str(SSD_ROOT / "tiles_contaminated")   # built by --build-contaminated
TILES_BLIND_NEG    = str(SSD_ROOT / "tiles_blind_neg")      # built by --build-blind-negatives
TILES_CONTAM_HEAVY = str(SSD_ROOT / "tiles_contam_heavy")   # the high-dose condition

# ── derived: slides, outputs, logs ───────────────────────────────────────────
SLIDES          = str(SSD_ROOT / "slides")
SLIDES_CONTAM   = str(SSD_ROOT / "slides_contam")
ABLATIONS       = str(SSD_ROOT / "ablations")
RUNS_V3         = str(SSD_ROOT / "runs_v3")
DEPLOY_MODELS   = str(SSD_ROOT / "deploy_models")
ABLATIONS_LOG   = str(SSD_ROOT / "ablations_detached.log")
SUPERVISOR_LOG  = str(SSD_ROOT / "supervisor.log")

# ── derived: the negative-screening models ───────────────────────────────────
SCREENER_DIR     = str(SSD_ROOT / "screener")
SCREENER_WEIGHTS = str(SSD_ROOT / "screener" / "run" / "weights" / "best.pt")
SCREENER_YAML    = str(SSD_ROOT / "screener" / "screener.yaml")

# ── derived: the pre-migration training tree on the HDD ──────────────────────
PLACENTA_TRAINING       = str(MIGRATION_ROOT / "placenta_training")
PLACENTA_TRAINING_CLEAN = str(MIGRATION_ROOT / "placenta_training_clean")
YOLO_V1_REPO            = str(MIGRATION_ROOT / "Yolo11_training-yolo11_train_seg_classify")
# the trusted pre-contamination detector (dated 2026-06-05, before the first NDPA overwrite)
TRUSTED_MODEL = str(MIGRATION_ROOT / "Yolo11_training-yolo11_train_seg_classify"
                    / "blood_vessel_best_BACKUP.pt")

# ── plain strings for the roots themselves ───────────────────────────────────
SSD_ROOT_STR       = str(SSD_ROOT)
SLIDES_DRIVE_STR   = str(SLIDES_DRIVE)
BACKUP_ROOT_STR    = str(BACKUP_ROOT)
MIGRATION_ROOT_STR = str(MIGRATION_ROOT)
REPO_ROOT_STR      = str(REPO_ROOT)


if __name__ == "__main__":
    print("configurable roots (environment variable -> resolved value):\n")
    for env, val in [("PLACENTA_SSD_ROOT", SSD_ROOT), ("PLACENTA_SLIDES_ROOT", SLIDES_DRIVE),
                     ("PLACENTA_BACKUP_ROOT", BACKUP_ROOT),
                     ("PLACENTA_MIGRATION_ROOT", MIGRATION_ROOT),
                     ("PLACENTA_REPO_ROOT", REPO_ROOT)]:
        mark = "set" if env in os.environ else "default"
        print(f"  {env:<26} {mark:<8} {val}")
    print("\nderived:\n")
    for name in sorted(n for n in dir() if n.isupper() and not n.endswith("_STR")
                       and isinstance(globals()[n], str)):
        print(f"  {name:<20} {globals()[name]}")
