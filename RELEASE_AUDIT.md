# Release audit

Audit trail for the assembly of this repository as the MICAD 2026 code artifact.
Generated 2026-08-21.

**Nothing in this repository was edited.** Every `.py`, `.yaml` and `.json` file was
SHA-256 hashed before any file was touched and re-hashed afterwards; the two multisets
are identical (708 files, see [Content-integrity proof](#content-integrity-proof)).
The only new files are `README.md`, `LICENSE`, `CITATION.cff`, `.gitignore`,
`requirements.txt` and this file. Everything else is a move.

**Nothing was deleted.** Material that should not ship was moved to
`_EXCLUDED_FROM_RELEASE/` for review, not removed.

---

## 1. Method, and the one place this audit deviates from the brief

The starting tree held **167,495 files across ~175 GB**. A per-file, one-line
description for all of them is not a useful document, so the inventory is:

- **file-level, with a description read from the file itself**, for all code, configs,
  manifests, results and documentation — the ~500 files that constitute the release;
- **directory-level, with file counts and byte totals**, for the ~165,000 tile images,
  label `.txt` files and archived training outputs.

Everything flagged in the sections below is enumerated exhaustively regardless of type.

### Starting layout

The repository was not under version control (`git rev-parse` fails; every run manifest
records `"git_commit": "no_git_repo"`, consistent with the brief). Three top-level
directories held everything:

| directory | size | what it was |
|---|---|---|
| `PLACENTA SLIDES/` | 97 GB | whole-slide images, pathologist and machine-written annotations, and several generations of derived tiles |
| `placenta_BACKUP/` | 78 GB | a `backup.py` snapshot **plus** the entire Windows GPU-migration working tree, which is where the real experimentation code lives |
| `figure_crops/` | 142 MB | 96 PNG crops of patient tissue prepared for figures, plus `crop_manifest.json` |

`placenta_BACKUP/.git` is not a directory but a 61-byte gitdir pointer to
`/Users/yugeshsarikonda/git-repos/placenta_BACKUP.git`, which is off this volume and was
not consulted.

---

## 2. Provenance of the released code

### 2.1 The decisive finding

**Two copies of `rigor/` existed.** They are not two variants of the same thing — one is
a pre-run snapshot of the other, and it is broken.

| | `placenta_BACKUP/rigor/` | `.../Yolo11_training-..._v2/rigor/` |
|---|---|---|
| origin | written by `backup.py`, which does `copytree(SRC_RIGOR, dest/rigor)` | the live working directory |
| created | `manifest.json` records `"created": "20260712_062737"` | — |
| mtimes | **all identical** (2026-07-26 11:25:52) — flattened by the copy | staggered 2026-07-10 → 2026-07-14, authentic |
| module count | 30 files | 43 files |
| `ablations.py`, `run_ablations.py`, `build_contaminated.py`, `build_heavy.py`, `launch_detached.py`, `supervisor.py`, `status.py` | **absent** | present |
| `tiling_config.py` | 8,365 bytes | 8,548 bytes |

Three independent lines of evidence identify the second copy as the code that ran:

**(a) `docs/release_tree.txt` declares the byte sizes.** This file was written by
`build_handoff.py` at handoff time (2026-07-14 13:19), after all eight runs finished. It
records a size for each released module. The `_v2/rigor` copy matches **every** declared
size; the backup copy matches all of them except one:

```
file                      declared   _v2/rigor   backup/rigor
slides_clean.yaml            5,947     5,947 ✓     5,947 ✓
tiling_config.py             8,548     8,548 ✓     8,365 ✗
tiling_fingerprint.py        5,766     5,766 ✓     5,766 ✓
backup.py                    5,255     5,255 ✓     5,255 ✓
contamination_audit.py       4,781     4,781 ✓     4,781 ✓
regen_negatives.py          12,710    12,710 ✓    12,710 ✓
tile_provenance.py           7,734     7,734 ✓     7,734 ✓
```

**(b) `rigor/run_manifest.json` records the hash *and its input payload* together.** It
stores `"tiling_hash": "7b191fa9e02e"` alongside the full `tiling` dict that was hashed.
Executing `as_dict()` from each candidate and comparing to that recorded dict:

- `_v2/rigor/tiling_config.py` → **reproduces the recorded payload exactly**, key for
  key, value for value.
- `placenta_BACKUP/rigor/tiling_config.py` → **raises `NameError` and produces nothing.**

**(c) The backup copy cannot have produced any run.** It is a half-finished rename caught
mid-edit: line 94 defines `NEG_SCREEN_MODELS` (plural) but line 153 of `as_dict()` still
reads `NEG_SCREEN_MODEL` (singular). Since `tiling_fingerprint.fingerprint()` calls
`as_dict()`, and `ablations.assert_c3()` calls `fingerprint()`, and `run_ablations.py`
calls `assert_c3()` before writing anything, this file would abort every run at import.
It is not a rival candidate; it is a broken intermediate that the backup happened to
capture 8 hours before the file was finished.

That timeline is internally consistent: backup at 2026-07-12 06:27:37 → `tiling_config.py`
finished at 2026-07-12 14:34:50 → first run 2026-07-13 08:23. It also explains why the
backup lacks seven modules: every one of them was written after the backup was taken.

**The `_v2/rigor` copy is what this repository ships. The backup copy is quarantined at
`_EXCLUDED_FROM_RELEASE/placenta_BACKUP/rigor/`.**

### 2.2 The causal chain, verified

```
run_ablations.py  --run <NAME>
      └─ ablations.assert_c3()
            └─ tiling_fingerprint.fingerprint()
                  ├─ tiling_config.as_dict()                      → param_hash
                  ├─ slide_registry.load_clean_slides()           → slides_hash   (C2)
                  └─ corpus_hash over every label byte + image size
            → composite must equal REQUIRED_HASH = "7b191fa9e02e", else sys.exit
```

`ablations.py` hard-codes `REQUIRED_HASH = "7b191fa9e02e"` and `HELD_OUT = "BFD_1"`. All
eight manifests record that hash and that held-out slide. Since no run can start unless
the assertion passes, every run necessarily executed against a `tiling_config.py` whose
`as_dict()` produced the recorded payload — which only the shipped copy does.

### 2.3 Cross-check against the eight manifests

All eight agree with the brief's stated ground truth, exactly and without exception:

- `tiling_hash` = `7b191fa9e02e` (8/8) · `tiling_method` = `vessel_centered_v3` (8/8)
- `held_out_slide` = `BFD_1` (8/8) · `arch` = `single_allmag` (8/8)
- `ultralytics` = `8.4.91` (8/8) · `python` = `3.12.10` (8/8)
- `command` = `python run_ablations.py --run <NAME>` (8/8, names as listed)
- `epochs`=300, `patience`=60, `imgsz`=1024, `batch`=16, `seed`=0, `deterministic`=true,
  `mixup`=0.0, `copy_paste`=0.0, `hsv_h`=0.005, `hsv_s`=0.05, `hsv_v`=0.1 (8/8)
- `mosaic` = 0.0 for seven runs, **1.0 for `pilot_mosaic1` only** — as stated

Run window, from file mtimes: **2026-07-13 08:23:24 → 2026-07-14 10:54:40.**

### 2.4 Verdict table

| module | verdict | evidence |
|---|---|---|
| `rigor/tiling_config.py` | **CONFIRMED** | `as_dict()` reproduces the payload recorded beside hash `7b191fa9e02e` in `run_manifest.json`; size 8,548 matches `release_tree.txt`; mtime 07-12 14:34 predates first run. Gates read `SNUG_FRAC=0.80`, `MIN_VISIBLE_FRAC=0.35`, `TILE_SIZE=1024` — all as specified. |
| `rigor/tiling_fingerprint.py` | **CONFIRMED** | size 5,766 matches `release_tree.txt`; mtime 07-11 00:40 predates all runs; is the C3 module the chain in §2.2 runs through. |
| `rigor/ablations.py` | **CONFIRMED** | hard-codes `REQUIRED_HASH = "7b191fa9e02e"` and `HELD_OUT = "BFD_1"`, both matching all 8 manifests; mtime 07-13 05:00 predates first run by 3 h 23 m. |
| `rigor/run_ablations.py` | **CONFIRMED**, with a timing caveat — see §2.5 | accepts `--run`; defines all eight run names; imports `tiling_config` and `ablations`; writes the `"command"` string found verbatim in all 8 manifests. |
| `rigor/slides_clean.yaml` | **CONFIRMED** | size 5,947 matches `release_tree.txt`; `confirmed: true`; the 11-slide include list matches the train+val slide lists in the manifests; mtime 07-11 02:12 predates all runs. |
| `rigor/backup.py` | **CONFIRMED** | size 5,255 matches `release_tree.txt`; its `corpus_manifest()` reimplemented and run against the surviving corpus reproduces **3 of the 4 recorded label hashes byte-for-byte** (see §9). |
| `rigor/contamination_audit.py` | **CONFIRMED** | size 4,781 matches `release_tree.txt`; mtime 07-10 04:01, the oldest module, predates everything. |
| `rigor/regen_negatives.py` | **CONFIRMED** | size 12,710 matches `release_tree.txt`; implements the two-detector union + TTA that `tiling_config.NEG_SCREEN_MODELS` / `NEG_SCREEN_TTA` describe and that the recorded hash payload contains. |
| `rigor/tile_provenance.py` | **CONFIRMED** | size 7,734 matches `release_tree.txt`; mtime 07-10 12:52 predates all runs; produced `rigor/tiles_ledger.csv`, also shipped. |
| `rigor/build_contaminated.py` | **CONFIRMED** | mtime 07-13 05:01 predates first run by 3 h 22 m; builds the paired label-swap corpus that `A_contam_matched`'s manifest documents under `paired_label_swap`. |
| `rigor/build_heavy.py` | **CONFIRMED** | mtime 07-14 00:40 predates `A_contam_heavy` (07-14 10:21) by 9 h 41 m; builds exactly that condition. |
| `rigor/validate_tiles.py` | **LIKELY** | mtime 07-11 00:39 predates all runs and it is cited by name in `tiling_config.py`'s comments as the tool that caught the 5x downsample bug — but nothing ties it to a specific run, and it is not in `release_tree.txt`. |
| `rigor/launch_detached.py` | **LIKELY** | mtime 07-13 13:43 falls **inside** the run window. An operational launcher, not imported by the training path; consistent with the runs, no hard tie. |
| `rigor/supervisor.py` | **LIKELY** | mtime 07-13 13:57, inside the run window. `run_ablations.py:370` comments on a two-supervisor race, so a supervisor demonstrably ran — but that does not pin *this* revision. |
| `rigor/status.py` | **LIKELY** | mtime 07-14 02:14, inside the run window. Read-only reporting tool; no tie to a specific run. |
| **MISSING** | — | **None.** All fifteen documented modules are present. |
| **DIVERGENT** | — | **One:** `placenta_BACKUP/rigor/tiling_config.py` (8,365 B). Quarantined, not edited, not reconstructed. See §2.1. |

The remaining 24 `.py` files in the shipped `rigor/` are not in the brief's documented
list but are part of the same authentic directory, with mtimes in or before the run
window. They are assessed collectively as **LIKELY** and shipped with names unchanged.
`slide_registry.py` deserves individual note: it is **CONFIRMED** by the same chain, since
`tiling_fingerprint.py` imports it and C2 runs through it.

### 2.5 Caveat on `run_ablations.py` — please read

`run_ablations.py` has mtime **2026-07-14 10:21:04**. `A_contam_heavy`'s manifest was
written at **10:21:58** — 54 seconds later. The other seven runs had all completed by
10:13:54.

So the shipped copy is provably the version that ran `A_contam_heavy`, and it is the
only copy in existence — but it was **modified after the other seven runs finished**.
Whatever changed in that edit is not recoverable: there is no version control, and no
earlier copy survives. The diff is most plausibly the wiring-in of the heavy condition
(the research log records "a run that was built but never wired into the orchestrator"),
which would not affect the earlier seven, but that is inference, not evidence.

I am flagging it rather than resolving it. It is the single weakest link in the
provenance chain.

### 2.6 Two corrections to the brief's expectations

Neither is a defect; both are places where the brief's stated model of the code differs
from what the code does.

**`MIN_ANN_OVERLAP = 0.10` is not in `tiling_config.py`.** The brief lists it among the
gates that must match. It is not there, and its absence is correct: it is a constant of
the **old sliding-window tiler** (`prepare_training_tiles.py:154`, `ndpa_to_tiles.py:44`,
both at `0.10` as expected). `tiling_fingerprint.PARAM_NAMES` still lists the name, but
that list is dead code — `read_tiling_params()` was changed to import `tiling_config`
instead of static-parsing the old tiler, and the docstring explains why. The
vessel-centred equivalent is `MIN_VISIBLE_FRAC = 0.35`, which is present and correct.

**`ablations.py` does not define C1 through C5.** It asserts **C1 and C3** only. The full
set is distributed: C2 in `slide_registry.py`, C4 in `loso_v3.py` / `loso_splits.py`, C5
in `run_manifest.py:162`. C5 appears exactly once in the codebase.

---

## 3. Released tree — `rigor/`

| path | bytes | modified | description |
| `rigor/ablations.py` | 7,158 | 2026-07-13 05:00:10 | build the corpus-ablation conditions (MICAD handoff, §1a). |
| `rigor/annotation_scale_report.py` | 5,510 | 2026-07-11 00:05:06 | does each slide's ground truth actually populate |
| `rigor/backup.py` | 5,255 | 2026-07-11 20:57:28 | snapshot the irreplaceable artefacts. |
| `rigor/build_blind_negatives.py` | 5,903 | 2026-07-13 05:04:06 | reconstruct the UNSCREENED negatives (for ablation C). |
| `rigor/build_contaminated.py` | 2,924 | 2026-07-13 05:01:58 | tile the FABRICATED labels (for ablation A). |
| `rigor/build_handoff.py` | 15,442 | 2026-07-14 11:00:58 | assemble handoff/ per the brief's §3 contract. |
| `rigor/build_heavy.py` | 4,347 | 2026-07-14 00:40:06 | the fabrication-TRAINED condition (A_contam_heavy). |
| `rigor/contamination_audit.py` | 4,781 | 2026-07-10 04:01:32 | decide whether an .ndpa is pathologist ground truth |
| `rigor/labelimg_launch.py` | 5,794 | 2026-07-11 13:33:54 | run labelImg 1.8.6 on modern PyQt5 without the float/int crashes. |
| `rigor/launch_detached.py` | 2,227 | 2026-07-13 13:43:42 | start the ablation suite so it SURVIVES session teardown. |
| `rigor/loso_splits.py` | 7,316 | 2026-07-10 04:03:40 | leave-one-slide-out fold generator (constraints C1 + C4). |
| `rigor/loso_v3.py` | 9,687 | 2026-07-11 02:13:24 | LOSO fold generator over the vessel-centred corpus (4.3, C1, C4). |
| `rigor/merge_manual_tiles.py` | 3,958 | 2026-07-11 00:02:04 | fold the user's hand-verified tiles into the clean set. |
| `rigor/open_labelimg.py` | 2,479 | 2026-07-11 00:24:46 | open a re-tiled scale/split in labelImg for review. |
| `rigor/parallel_retile.py` | 5,889 | 2026-07-11 00:09:44 | same tiling as retile_clean.py, but across all CPU cores. |
| `rigor/pilot.py` | 6,144 | 2026-07-11 14:04:06 | measure the epoch budget the real grid needs, WITHOUT biasing it. |
| `rigor/preannotate_labelimg.py` | 9,932 | 2026-07-10 12:54:20 | model-assisted pre-annotation for labelImg, built so |
| `rigor/reconcile_negatives.py` | 4,006 | 2026-07-11 02:54:14 | make negatives exactly 1:1 with the SURVIVING positives. |
| `rigor/regen_negatives.py` | 12,710 | 2026-07-11 13:44:44 | rebuild ONLY the negative tiles: 1:1 with positives, and |
| `rigor/retile_clean.py` | 4,873 | 2026-07-10 13:16:34 | re-tile slides at 10x/20x/40x from AUDITED CLEAN .ndpa only. |
| `rigor/run_ablations.py` | 22,272 | 2026-07-14 10:21:04 | execute the ablation suite + epoch-cap pilot, and log the |
| `rigor/run_manifest.py` | 6,147 | 2026-07-11 14:03:32 | the source of truth for every training run (4.1). |
| `rigor/slide_registry.py` | 3,076 | 2026-07-10 04:01:06 | the single gate for constraint C2. |
| `rigor/stage_to_ssd.py` | 2,027 | 2026-07-11 00:04:58 | move the tiling working set onto the NVMe SSD. |
| `rigor/status.py` | 3,701 | 2026-07-14 02:14:18 | one command, the whole truth. Reads from disk, never from memory. |
| `rigor/supervisor.py` | 6,756 | 2026-07-13 13:57:54 | keep the ablation suite running to completion, unattended. |
| `rigor/tile_provenance.py` | 7,734 | 2026-07-10 12:52:12 | a per-tile verification ledger (refines constraint C2). |
| `rigor/tile_vessel_centered.py` | 10,232 | 2026-07-11 00:34:40 | the CORRECTED tiler. Vessel-centred, not sliding-window. |
| `rigor/tiling_config.py` | 8,548 | 2026-07-12 14:34:50 | the single source of truth for tiling parameters (feeds 4.2). |
| `rigor/tiling_fingerprint.py` | 5,766 | 2026-07-11 00:40:50 | constraint C3. |
| `rigor/topup_5x_negatives.py` | 9,579 | 2026-07-11 20:47:42 | generate MORE 5x negatives for manual verification. |
| `rigor/train_deploy_models.py` | 4,364 | 2026-07-12 15:01:20 | the PRODUCTION detectors. NOT part of the paper. |
| `rigor/train_run.py` | 4,926 | 2026-07-11 02:14:46 | trainer wrapper for one run of the manifest (4.4). |
| `rigor/train_screener.py` | 2,627 | 2026-07-11 13:59:48 | train the high-recall detector used to SCREEN negative tiles. |
| `rigor/validate_tiles.py` | 4,536 | 2026-07-11 00:39:06 | prove the tiles actually frame the vessel. |

## 4. Released tree — data, results, docs

| path | bytes | modified | description |
|---|---|---|---|
| `rigor/run_manifest.json` | 247,595 | 2026-07-12 14:35:28 | Generated run manifest: records `tiling_hash` 7b191fa9e02e together with the full tiling parameter payload, plus the planned 264-cell grid definition. Written by `rigor/run_manifest.py`. |
| `rigor/tiles_ledger.csv` | 219,984 | 2026-07-10 12:52:18 | Per-tile provenance ledger (1,912 tiles): tile_id, slide, scale, kind, n_boxes, label SHA, image bytes, verification status. Written by `rigor/tile_provenance.py`. |
| `rigor/slides_clean.yaml` | 5,947 | 2026-07-11 02:12:30 | **C2** — the frozen 11-slide allow-list, `confirmed: true`, with per-slide exclusion reasons. The loader refuses to fall back to globbing. |
| `results/results.json` | 10,912 | 2026-07-14 11:01:12 | Aggregated machine-readable ablation results for all 8 runs in the brief's §3.1 schema, plus the epoch-cap pilot. |
| `results/corpus_checksums.json` | 903 | 2026-07-14 13:18:48 | Per-scale/split image counts and SHA-based label-content hashes for the 8 corpus splits, re-verified against the live corpus at handoff time. |
| `results/verification.md` | 17,224 | 2026-07-14 13:14:22 | Item-by-item confirmation or correction of every claim the runs touch (V1-V10). V9 is the key correction on fabrication dose. |
| `results/RESEARCH_LOG.md` | 26,633 | 2026-07-14 10:57:50 | Lab notebook, 20 dated entries: bugs found mid-suite, corrected overclaims, and the reasoning behind each design change. |
| `results/RUN_QUEUE.md` | 6,819 | 2026-07-14 10:58:52 | The 8 results with a plain-language finding per ablation and 6 cross-cutting limitations for the paper. |
| `docs/HANDOFF.md` | 6,639 | 2026-07-14 13:19:58 | Handoff index: headline metrics table for all 8 runs, reading order, the three findings that matter most, and the limitations list. |
| `docs/RELEASE_README.md` | 2,992 | 2026-07-14 13:16:14 | FAIR release description: component table, verification commands, and the C1-C5 definitions used as the source for this repository's README. |
| `docs/release_manifest.md` | 2,398 | 2026-07-14 13:19:14 | One-line purpose for every component of the FAIR release bundle. |
| `docs/release_tree.txt` | 1,373 | 2026-07-14 13:19:06 | Release bundle tree with **declared byte sizes** — the artifact used in this audit to identify which `tiling_config.py` actually ran. |
| `results/plots/qc_A_fabrication.png` | 21,059 | 2026-07-14 11:01:12 | QC sanity-check plot (not a publication figure). |
| `results/plots/qc_B_tiling.png` | 19,637 | 2026-07-14 11:01:12 | QC sanity-check plot (not a publication figure). |
| `results/plots/qc_C_negatives.png` | 19,593 | 2026-07-14 11:01:12 | QC sanity-check plot (not a publication figure). |
| `results/plots/qc_convergence.png` | 171,189 | 2026-07-14 11:01:12 | QC sanity-check plot (not a publication figure). |
| `results/plots/qc_inflation_flip.png` | 20,154 | 2026-07-14 11:01:12 | QC sanity-check plot (not a publication figure). |
| `rigor/splits_v3/` (133 files) | — | 2026-07-11 | LOSO fold definitions: `loso_folds.json` + per-fold dataset YAMLs and the train/val image lists Ultralytics reads. Supports C1/C4. |

### `runs/` — the archived experimental record

Each directory holds `manifest.json`, `args.yaml`, `metrics_final.json` and the raw
unedited per-epoch `results.csv`. **No `.pt` weight files** — all 16 were moved to
`_EXCLUDED_FROM_RELEASE/weights/runs/`.

| run | tiling_hash | mosaic | train imgs | val imgs | mAP50 | bytes | modified |
|---|---|---|---|---|---|---|---|
| `A_contam_asitwas` | 7b191fa9e02e | 0.0 | 6,030 | 489 | 0.89078 | 15,222 | 2026-07-14 13:11 |
| `A_contam_fabval` | 7b191fa9e02e | 0.0 | 5,511 | 489 | 0.88152 | 17,415 | 2026-07-14 13:11 |
| `A_contam_heavy` | 7b191fa9e02e | 0.0 | 1,224 | 489 | 0.19394 | 12,743 | 2026-07-14 13:11 |
| `A_contam_matched` | 7b191fa9e02e | 0.0 | 5,358 | 489 | 0.89164 | 17,174 | 2026-07-14 13:11 |
| `B_sliding_window` | 7b191fa9e02e | 0.0 | 5,071 | 489 | 0.8705 | 19,353 | 2026-07-14 13:11 |
| `C_blind_negatives` | 7b191fa9e02e | 0.0 | 5,303 | 489 | 0.86795 | 16,620 | 2026-07-14 13:11 |
| `baseline` | 7b191fa9e02e | 0.0 | 5,303 | 489 | 0.89017 | 17,565 | 2026-07-14 13:11 |
| `pilot_mosaic1` | 7b191fa9e02e | 1.0 | 5,303 | 489 | 0.86716 | 20,528 | 2026-07-14 13:11 |

---

## 5. Whole-slide images and annotation files

Pattern scan for `*.ndpi`, `*.ndpa`, `*.svs`, `*.tif`, `*.tiff`.

| type | count | total | disposition |
|---|---|---|---|
| `.ndpi` whole-slide images | 31 | 81.7 GiB | **moved to `/Volumes/Extreme SSD/PLACENTA_SLIDES/`** |
| `.ndpa` annotation files | 63 | 2.4 GiB | **moved to `/Volumes/Extreme SSD/PLACENTA_SLIDES/`** |
| AppleDouble sidecars for the above | 36 | 144 KB | moved alongside their data files |
| `.tif` | 2,235 | 6.55 GiB | **not** whole-slide images — every one is a 1–50 MB training tile inside a `training_data_*/**/images/` directory. Moved to `_EXCLUDED_FROM_RELEASE/tiles/`. |
| `.svs`, `.tiff` | 0 | — | none present |

**94 real patient files, 84.10 GiB, moved with zero failures and zero collisions.** The
internal folder structure was preserved verbatim under the destination root. Full
source→destination log with per-file byte counts: see the session report.

Repository now contains **zero** files matching `*.ndpi` or `*.ndpa`, verified after the
move. `.gitignore` blocks all five patterns.

### Post-move sweep for patient data and identifiers

Grepped the entire remaining tree for `.ndpi`, `.ndpa`, and the slide identifiers
`S.2058`, `S.2723`, `S.3152`, `A2FD`, `BFD_1`:

- **Slide IDs appear only inside manifests, configs, ledgers and code** — the allow-list,
  the run manifests' `train_slides`/`val_slides` arrays, `tiles_ledger.csv`, and
  `ablations.py`'s `FABRICATED` dict. This is expected and was confirmed acceptable.
- **`.ndpa` filenames appear as strings** in `runs/*/manifest.json` (`paired_label_swap`
  block) and `rigor/ablations.py`. These are *references*, not data.
- **No patient data files remain.** No emails anywhere in the release tree.
- One personal identifier: `rigor/slides_clean.yaml:21` reads
  `confirmed_by: "yugesh (authorised in session, 2026-07-11)"`. That is the author's own
  first name and forms part of the C2 ratification record. Flagged for a decision; left
  unedited.
- One directory name in the excluded tree contains what looks like a **real patient
  accession number** — a `CASE - N - [<accession>] - <block>` name, where the bracketed
  token is a laboratory accession of the form letter-hyphen-four-digits-hyphen-two-digits.
  The identifier itself is not reproduced here. It travelled to
  `/Volumes/Extreme SSD/PLACENTA_SLIDES/` with its `.ndpa` file. Worth a look — the
  bracketed token does not match this study's slide-ID convention.

---

## 6. Files over 50 MB

37 files, 84.9 GiB total. **None remain in the release tree.**

| file | size | disposition |
|---|---|---|
| 31 × `.ndpi` whole-slide images | 81.7 GiB | moved to `/Volumes/Extreme SSD/PLACENTA_SLIDES/` |
| `.../Yolo11_..._classify/runs/detect/train-2/weights/best.pt` | 154.2 MB | `_EXCLUDED_FROM_RELEASE/weights/` |
| `.../Yolo11_..._classify/runs/detect/train-2/weights/last.pt` | 154.2 MB | `_EXCLUDED_FROM_RELEASE/weights/` |
| `.../runs/train/placenta_10x_rebalanced/weights/best.pt` | 153.8 MB | `_EXCLUDED_FROM_RELEASE/weights/` |
| `.../runs/train/placenta_10x_rebalanced/weights/last.pt` | 153.8 MB | `_EXCLUDED_FROM_RELEASE/weights/` |
| `.../train_backups/v1_vessel_centered_.../placenta_10x_rebalanced_best.pt` | 153.8 MB | `_EXCLUDED_FROM_RELEASE/weights/` |
| `windows_gpu_migration/NDP.view 2.10.0 RUO Setup.zip` | 52.6 MB | `_EXCLUDED_FROM_RELEASE/placenta_BACKUP/` — a third-party vendor installer |

Largest file remaining anywhere in the release tree: `rigor/run_manifest.json`, 247,595 bytes.

---

## 7. Model weights

**160 files, 3.69 GiB — all excluded, none in the release tree.**

| group | count | destination |
|---|---|---|
| per-run `best.pt` / `last.pt` for the 8 ablation runs | 16 | `_EXCLUDED_FROM_RELEASE/weights/runs/<run>/` |
| `rigor/yolo11n.pt`, `rigor/yolo26n.pt` (pretrained seeds) | 2 | `_EXCLUDED_FROM_RELEASE/weights/rigor_*.pt` |
| all other `.pt` in the archived training trees | 141 | `_EXCLUDED_FROM_RELEASE/weights/<original path>` |
| `.onnx` | 1 | `_EXCLUDED_FROM_RELEASE/weights/<original path>` |
| `.pth` | 0 | — |

Original paths are preserved beneath `_EXCLUDED_FROM_RELEASE/weights/` so the provenance
of each weight file is still readable. Verified: zero `.pt`/`.pth`/`.onnx` outside the
exclusion directory.

Note that `screener/best.pt` — the second detector in the negative-screening union — is
among these. It is a genuine input to the corpus construction, not a training output.

---

## 8. Tile image directories

**20 tile-corpus roots, 47,448 files, 50.4 GiB** → `_EXCLUDED_FROM_RELEASE/tiles/`,
original paths preserved.

| root | files | size |
|---|---|---|
| `placenta_BACKUP/tiles_v3` (the ratified `vessel_centered_v3` corpus) | 7,855 | 12.6 GB |
| `placenta_training/training_data_{10x,20x,40x}_v2_wholeslide_flawed_*` | 14,919 | 13.1 GB |
| `placenta_training/training_data_{10x,20x,40x,5x}` + `_v1_vessel_centered_*` + `_STALE_BACKUP_*` | 9,942 | 10.6 GB |
| `PLACENTA SLIDES/placenta/training_data_{5x,10x,20x,40x}` + `_v1_vessel_centered_*` + `_BACKUP_before_downsample_fix` | 13,560 | 13.0 GB |

The `_v2_wholeslide_flawed_` directories are the output of the abandoned sliding-window
tiler — the same tiling the `B_sliding_window` ablation isolates.

---

## 9. Corpus integrity — a defect you should know about

While testing whether the shipped `backup.py` could reproduce the recorded checksums, I
reimplemented its `corpus_manifest()` and ran it against `placenta_BACKUP/tiles_v3`.
Comparing to the recorded hashes in `placenta_BACKUP/manifest.json`:

| split | recorded | recomputed | images | verdict |
|---|---|---|---|---|
| `10x/positives` | `648bcb18fedf56f7` | `648bcb18fedf56f7` | 753 / 753 | **MATCH** |
| `10x/negatives` | `03d260d9fc1d6e2d` | `03d260d9fc1d6e2d` | 253 / 253 | **MATCH** |
| `20x/negatives` | `d5420bc61cbc6af3` | `d5420bc61cbc6af3` | 755 / 755 | **MATCH** |
| `20x/positives` | `9f54f21631817cbd` | `2ad0cbbd7ef4fe77` | 1,543 / 1,543 | **MISMATCH** |
| `40x/positives` | `d6b25b92a4c9b282` | — | 1,244 / **0** | **ABSENT** |
| `40x/negatives` | `ed2f18c5a30ab909` | — | 1,244 / **0** | **ABSENT** |
| `5x/positives` | `788f27fea920be68` | — | 54 / **0** | **ABSENT** |
| `5x/negatives` | `feae3933088c1716` | — | 59 / **0** | **ABSENT** |

Three of the four surviving splits reproduce their recorded SHA-256 label hash exactly —
strong independent confirmation both that `backup.py` is the genuine article and that
those tiles are byte-identical to the ones used.

**But this backup is incomplete:**

- `training_data_40x` and `training_data_5x` are **entirely missing** — 2,601 tiles.
- `20x/positives` has all 1,543 images but only 434 label files: **1,109 labels are
  missing.** That is the sole cause of its hash mismatch; the image set is intact.

`backup.py --verify` exists precisely to catch this and appears not to have been run
against this copy. Since the labels are the hand-reviewed, irreplaceable part — `backup.py`'s
own docstring says 566 of 756 10x labels were edited by hand — this is worth attention
independently of the release. The corpus is not shipped either way.

Consequence for verification: **the tiling hash `7b191fa9e02e` cannot be recomputed from
anything on this volume**, because `corpus_hash` walks 10x, 20x *and* 40x, and 40x is gone.
The provenance conclusions in §2 rest on the payload comparison instead, which does not
need the corpus.

### 9b. Diagnosis (added in round 2): this is an interrupted copy, not data loss

The gap has a single, fully determined cause. File mtimes across `tiles_v3` form one
continuous, strictly alphabetical copy timeline on **2026-07-26**:

```
11:25:53.11  training_data_10x/negatives/images    253
11:25:55.05  training_data_10x/negatives/labels    263
11:25:55.48  training_data_10x/positives/images    753
11:26:31.61  training_data_10x/positives/labels    757
11:26:34.10  training_data_20x/negatives/images    755
11:26:42.77  training_data_20x/negatives/labels    762
11:26:44.59  training_data_20x/positives/images   1543
11:27:43.35  training_data_20x/positives/labels    434   <-- stops at 11:27:44.34
             training_data_40x                            directory never created
             training_data_5x                             directory never created
```

Two independent checks confirm a clean single truncation:

- The 434 surviving labels are **exactly the alphabetically-first 434** of the 1,543
  expected (`sorted(present) == sorted(all)[:434]` is `True`), and **zero** labels exist
  beyond the cut point. The cut falls mid-slide, between
  `S.2016_26_A2_FD_1_20x_0138664_0040532` (present) and
  `S.2016_26_A2_FD_1_20x_0142106_0068909` (missing).
- `40x` and `5x` sort after `20x`, so a copy that died inside `20x` would never reach
  them — which is exactly what the absent directories show.

The labels directory was being written for **0.99 seconds** before the copy stopped.

**The source corpus was complete.** `tiles_v3/_done/` holds **44 completion markers —
11 slides x 4 scales**, including all 11 for 40x and all 11 for 5x. The tiler finished
every scale on the source machine. Nothing was lost at the source; this copy simply never
finished.

**How far the `_done` markers go as evidence.** The markers evidence that the tiler ran to
completion, not that the output still exists at the source today. The 2026-07-13
`baseline` run reading all 5,792 images is the stronger evidence, and it establishes the
state on that date only.

This means the 1,109 hand-drawn labels are recoverable **if the copy source still
exists**. See §18.

---

## 10. Credentials, API keys, and secrets

Scanned all `.py`, `.yaml`, `.json`, `.md`, `.sh`, `.bat`, `.ps1`, `.ipynb`, `.cfg`,
`.toml`, `.ini` files for `password`, `passwd`, `api_key`, `secret`, `credential`,
`bearer`, `access_token`, and email addresses.

**No credentials found — in the release tree or anywhere else.** Every hit was one of:

1. documentation *about* redacting credentials (`docs/HANDOFF.md`, the original brief);
2. the redaction regex itself in `rigor/build_handoff.py:43`;
3. stock upstream YOLOv5 boilerplate — `# pipe = 'rtsp://username:password@192.168.1.64/1'`
   — in vendored `utils/datasets.py` copies, all of which are now in
   `_EXCLUDED_FROM_RELEASE/`.

No email addresses appear anywhere in the release tree.

---

## 11. Absolute paths retained in the archived record

**These are deliberately unaltered.** The files are the experimental record; their value
depends on being byte-for-byte as written.

| file | occurrences | content |
|---|---|---|
| `runs/baseline/manifest.json` | 1 | `config.project` = `D:\windows_gpu_migration\Yolo11_training-yolo11_train_seg_classify_v2\handoff\runs` |
| `runs/A_contam_matched/manifest.json` | 1 | same |
| `runs/A_contam_asitwas/manifest.json` | 1 | same |
| `runs/A_contam_fabval/manifest.json` | 1 | same |
| `runs/A_contam_heavy/manifest.json` | 1 | same |
| `runs/B_sliding_window/manifest.json` | 1 | same |
| `runs/C_blind_negatives/manifest.json` | 1 | same |
| `runs/pilot_mosaic1/manifest.json` | 1 | same |

The manifests also reference slide files by relative path inside their
`paired_label_swap` block (e.g. `PLACENTA SLIDES/A Files/…ndpa`). Those are references
to data that is not in the repository, not paths to anything present.

**Correction to the brief:** the `runs/*/args.yaml` files do **not** contain absolute
paths. `build_handoff.py` sanitised them at handoff time — they read
`project: <REPO>\handoff\runs` and `data: <DATA>\ablations\baseline\data.yaml`. All eight
were checked; zero contain a Windows drive letter. The README documents the manifest
paths as deliberate.

---

## 12. Absolute paths inside `.py` source — flagged separately, worth fixing by hand

This is the finding the brief asked to have separated out, and it is larger than one
file: **25 of the 35 shipped modules hard-code an absolute Windows path.** These are not
archived records — they are live source, and every one of them will fail on any other
machine.

| module | hard-coded paths |
|---|---|
| `ablations.py` | `C:\placenta_ssd\{tiles_v3,training_clean,tiles_contaminated,tiles_blind_neg,ablations}`, `D:\PLACENTA SLIDES` |
| `backup.py` | `C:\placenta_ssd\tiles_v3`, `C:\placenta_ssd\screener\run\weights\best.pt`, `D:\placenta_BACKUP` |
| `tiling_fingerprint.py` | `DATA_ROOT = C:\placenta_ssd\tiles_v3` |
| `regen_negatives.py` | `C:\placenta_ssd\{tiles_v3,slides}`, `C:\placenta_ssd\screener\...`, `D:\windows_gpu_migration\...` |
| `build_contaminated.py` | `C:\placenta_ssd\{tiles_contaminated,slides,slides_contam}` |
| `build_heavy.py` | `C:\placenta_ssd\{tiles_contam_heavy,slides_contam,slides}` |
| `build_blind_negatives.py` | `C:\placenta_ssd\{tiles_v3,slides}` |
| `run_ablations.py` | `C:\placenta_ssd\tiles_contam_heavy` |
| `validate_tiles.py` | `C:\placenta_ssd\tiles_v3` (×2), `C:\placenta_ssd\training_clean`, `D:\windows_gpu_migration\placenta_training` |
| `tile_provenance.py` | `D:\windows_gpu_migration\placenta_training` |
| `tile_vessel_centered.py` | `C:\placenta_ssd\{tiles_v3,slides}` |
| `loso_v3.py` | `C:\placenta_ssd\tiles_v3` |
| `loso_splits.py` | `D:\windows_gpu_migration\placenta_training` |
| `supervisor.py` | `C:\placenta_ssd\supervisor.log`, `C:\placenta_ssd\ablations_detached.log` |
| `launch_detached.py` | `C:\placenta_ssd\ablations_detached.log` |
| `reconcile_negatives.py` | `C:\placenta_ssd\tiles_v3` |
| `topup_5x_negatives.py` | `C:\placenta_ssd\{tiles_v3,slides,screener\...}`, `D:\windows_gpu_migration\...` |
| `train_deploy_models.py` | `C:\placenta_ssd\{tiles_v3,deploy_models}` |
| `train_screener.py` | `C:\placenta_ssd\screener\screener.yaml`, `C:\placenta_ssd\screener` |
| `run_manifest.py` | `C:\placenta_ssd\runs_v3` |
| `stage_to_ssd.py` | `C:\placenta_ssd` |
| `merge_manual_tiles.py` | `D:\windows_gpu_migration\placenta_training{,_clean}` |
| `parallel_retile.py` | `D:\windows_gpu_migration\placenta_training_clean` |
| `retile_clean.py` | `D:\windows_gpu_migration\placenta_training_clean` |
| `annotation_scale_report.py` | `D:\PLACENTA SLIDES` — **the only one with an env override**: `os.environ.get("PLACENTA_SLIDES_ROOT", …)` |

`rigor/slides_clean.yaml` also mentions `D:\PLACENTA SLIDES` in two comment lines
(lines 8 and 37).

None of these were edited. `annotation_scale_report.py`'s `PLACENTA_SLIDES_ROOT`
environment-variable pattern is the obvious template if you decide to fix them.

---

## 13. Duplicate and near-duplicate scripts

Searched for `_v2`, `_old`, `_final`, `copy`, `backup`, `bak`, `tmp`, `test`, `scratch`,
`WIP` in filenames, and for repeated basenames.

**Inside the release tree: none.** `rigor/` holds 35 distinctly-named modules with no
duplicate basenames and no versioned variants.

The pairs that mattered were resolved in §2 and are quarantined:

| duplicate | resolution |
|---|---|
| `rigor/tiling_config.py` — two copies, 8,548 B vs 8,365 B | 8,548 B shipped (CONFIRMED); 8,365 B quarantined (DIVERGENT, and non-executing) |
| `rigor/{tiling_fingerprint,backup,contamination_audit,regen_negatives,tile_provenance,validate_tiles,slides_clean.yaml,…}` — two copies each | byte-identical; the `_v2` copy shipped, the backup copy quarantined with its directory |

The excluded tree contains many more, all left intact for review — notably
`Yolo11_training-yolo11_train_seg_classify` vs `…_v2` (two full generations of the
project), `utils/backup dump/` with `datasets - Copy.py`, `datasets - failed.py`,
`datasets_backup.py`, `datasets_shr.py`, and the `_v1_vessel_centered_*` /
`_v2_wholeslide_flawed_*` / `_STALE_BACKUP_*` / `_BACKUP_before_downsample_fix` tile
generations.

---

## 14. What was excluded, and why

| location | files | size | why |
|---|---|---|---|
| `_EXCLUDED_FROM_RELEASE/PLACENTA SLIDES/` | 80 | 0.00 GiB |
| `_EXCLUDED_FROM_RELEASE/figure_crops/` | 98 | 0.12 GiB |
| `_EXCLUDED_FROM_RELEASE/placenta_BACKUP/` | 36,046 | 28.58 GiB |
| `_EXCLUDED_FROM_RELEASE/tiles/` | 47,448 | 41.19 GiB |
| `_EXCLUDED_FROM_RELEASE/weights/` | 160 | 3.69 GiB |

Reasons, by group:

- **`weights/`** (160 files, 3.69 GiB) — large binaries; git is the wrong host. Includes
  the 16 per-run `best.pt`/`last.pt` the release layout explicitly excludes.
- **`tiles/`** (47,448 files, 41.2 GiB) — the derived tile corpus. Reconstructible
  imagery of patient specimens; not redistributable.
- **`placenta_BACKUP/`** (36,046 files, 28.6 GiB) — the whole Windows working tree after
  the release material was lifted out of it: two generations of the YOLO project, vendored
  upstream YOLOv5 `utils/`, prediction outputs, training logs (several single log files
  exceed 2 MB), a vendor installer `.zip`, `.claude/` session directories, and the
  quarantined `placenta_BACKUP/rigor/` snapshot from §2.1.
- **`PLACENTA SLIDES/`** (80 files, ~20 MB) — what remained after the `.ndpi`/`.ndpa`
  files and tile directories were moved out: annotation working directories, per-scale
  scratch folders, and a vendored `zinference/` copy of YOLOv5.
- **`figure_crops/`** (98 files, 142 MB) — 96 PNG crops of patient tissue prepared for
  paper figures, plus `crop_manifest.json` and a `gallery/`. **These are patient imagery.**
  They are not slides, so they fell outside the `.ndpi`/`.ndpa` move rule, but they should
  not be published as-is. Flagged for your decision.

---

## 15. Content-integrity proof

Every `.py`, `.yaml`, `.yml` and `.json` file in the tree was SHA-256 hashed **before any
file was moved**, and re-hashed afterwards across both the repository and the slide
destination.

```
baseline : 708 files   (386 .py, 287 .yaml, 35 .json)
after    : 708 files
multiset of SHA-256 digests: IDENTICAL
```

No file's content changed, and none was lost. The 708 count includes 297 macOS
AppleDouble `._*` sidecars that happen to carry those extensions; excluding them, 411
real source and config files were tracked.

---

## 16. Open items from round 1 — status after round 2

| # | item | status |
|---|---|---|
| 1 | `configs/slides_clean.yaml` breaks the C2 loader | **RESOLVED** — moved back to `rigor/slides_clean.yaml`; `configs/` removed. Single copy only. |
| 2 | `prepare_training_tiles.py` absent, 7 modules import it | **CLOSED AS A DELIBERATE EXCLUSION.** Moved into `rigor/` in round 2, withdrawn in round 3 because it hard-codes specimen identifiers. The seven imports are unresolved by design and documented in `README.md`. See §17. |
| 3 | paper title and DOI unknown | **RESOLVED for title/venue/series/authors**, supplied by the author. DOI remains a marked `TODO` — not assigned until publication. |
| 4 | `run_ablations.py` edited mid-suite | **UNRESOLVED AND UNRESOLVABLE** — see §2.5. Now recorded plainly in `README.md` under "Provenance of this code". |
| 5 | `figure_crops/` is patient imagery in a review folder | **RESOLVED** — moved to `/Volumes/Extreme SSD/PLACENTA_SLIDES/figure_crops/`. 98 files, 129,086,171 bytes. |
| 6 | accession-style identifier in an excluded directory name | **RESOLVED** — that file is on the SSD. Shipping `prepare_training_tiles.py` briefly reintroduced accession numbers as *strings*; in round 3 that file was withdrawn. See §17. |

**Judgment calls from round 1 that still stand:** `RELEASE_README.md` in `docs/`, the five
QC plots in `results/plots/`, and `run_manifest.json` / `tiles_ledger.csv` / `splits_v3/`
left in `rigor/` beside their generators.

---

## 17. `prepare_training_tiles.py` — shipped in round 2, withdrawn in round 3

**Final state: excluded.** The file is at `_EXCLUDED_FROM_RELEASE/prepare_training_tiles.py`,
byte-identical to the copy that ran (SHA-256 `7e520de5…`, 18,387 bytes, mtime 2026-07-08,
predating every run).

**Why it was shipped in round 2.** Three reasons, all still valid: seven `rigor/` modules
import it; it implements the sliding-window tiler behind the `B_sliding_window` baseline;
and it defines `MIN_ANN_OVERLAP = 0.10`, a constant the paper states explicitly.

**Why it was withdrawn in round 3.** Its `SLIDE_PAIRS` list hard-codes laboratory
accession identifiers for **three specimens** — ten string occurrences in total — in
`CASE - N - [<accession>] - <block>` filenames. None of those three slides is in the
ratified 11-slide allow-list, and none appears in the paper. The accessions are not
reproduced in this audit, in the README, or anywhere else in the release tree; naming them
to document them would defeat the point. None of the three reasons for shipping the file
requires that list, so the identifiers bought nothing. Withdrawing it also keeps every
shipped file byte-identical to what ran, which is what the provenance argument in §2 rests
on.

The module additionally carried 24 macOS absolute paths (`/Volumes/...`). With it
withdrawn, **the absolute-path module count returns to 25** (§12), and the release tree
again contains **no `/Volumes/` or `/Users/` path anywhere**.

**Cost of the withdrawal, and how it is documented.** `README.md` records all three
consequences under "Known limitations of this release": that the file is deliberately
excluded because it hard-codes specimen identifiers and is available on request through
the corpus channel; that `MIN_ANN_OVERLAP = 0.10` means a tile counted as positive on a
10% sliver of an annotated vessel with the box drawn around the sliver, so the paper's
claim is checkable without the file; and that the C3 chain does not touch it, so corpus-hash
verification is unaffected.

**Import scan, re-run after the withdrawal.** Over the 35 remaining `rigor/` modules, one
import is unresolved — `prepare_training_tiles`, in exactly seven modules:

```
annotation_scale_report.py   build_blind_negatives.py   parallel_retile.py
regen_negatives.py           retile_clean.py            tile_vessel_centered.py
topup_5x_negatives.py
```

They import `parse_ndpa_bboxes`, and `retile_clean.py` / `parallel_retile.py` also import
`extract_tiles_for_scale` — annotation-parsing and tile-extraction helpers, not the
identifier list. Every other import across those 35 modules resolves to a stdlib module, a
module present in `rigor/`, or a package listed in `requirements.txt`.

**Accession sweep of the release tree.** Zero matches for the shape
`S[-.]\d{4,5}-\d{2}` — in filenames, in directory names, and in file contents, this audit
included. The study's own slide IDs (`S.2058_26`, `BFD_1`, `A2FD_1`, …) appear as expected
in manifests, the allow-list, `tiles_ledger.csv`, `splits_v3/` image lists and code, and
were not altered.

---

## 18. Corpus recovery — where to look next

This is the separate data-integrity task, reported here so it stays with the record.
**Nothing was copied, moved, synced or deleted.**

**Searched — exhaustively.** Two methods, run independently, agreeing exactly:

1. A full `find` walk of both mounted volumes — `Extreme SSD` (exFAT, external) and
   `Macintosh HD` (APFS, internal, including `/System/Volumes/Data`) — for any directory
   named `tiles_v3` or `training_data_*`. Ran 2026-08-21 18:55:55 → 19:29:59 (34 min),
   completed, exit 0.
2. A Spotlight (`mdfind`) cross-check over the same name patterns.

Also checked: the SSD `$RECYCLE.BIN` (one unrelated item from 2023-08),
`/Volumes/Extreme SSD/.Trashes` (empty), `~/.Trash` (empty), and the bare git repository
at `~/git-repos/placenta_BACKUP.git`.

**The exhaustive walk found nothing the Spotlight check had not already surfaced.** Its
only internal-drive hits were under `/Users/yugeshsarikonda/placenta_training/`, listed
twice because `/Users` is a firmlink to `/System/Volumes/Data/Users` — the same directory
reached by two paths, not two copies. **There is no `tiles_v3` anywhere on the internal
drive.**

**Found on the SSD** — every `tiles_v3` / `training_data_*` directory:

| root | layout | v3 splits found | recorded hashes reproduced |
|---|---|---|---|
| `_EXCLUDED_FROM_RELEASE/tiles/placenta_BACKUP/tiles_v3` | v3 (`<scale>/{positives,negatives}/{images,labels}`) | 4 of 8 | **3 of 8** (10x/pos, 10x/neg, 20x/neg) |
| `_EXCLUDED_FROM_RELEASE/tiles/PLACENTA SLIDES/placenta` | old (`train/{positives,negatives}` + `val` + `test`) | none | 0 — `corpus_manifest()` sees nothing |
| `_EXCLUDED_FROM_RELEASE/tiles/.../placenta_training` | old (same) | none | 0 — `corpus_manifest()` sees nothing |
| `/Users/yugeshsarikonda/placenta_training` (internal drive, 21 GB) | old (same), pre-v3, dated 2026-07-02..09 | none | 0 — `corpus_manifest()` sees nothing |
| `~/git-repos/placenta_BACKUP.git` (bare, 37 GB, 70,306 tracked files) | tracks `tiles_v3/` | **the same truncated state** | n/a — see below |

The old-layout roots include `training_data_40x` directories, but they are **pre-v3
generations** (dated 2026-07-03, and the `_v2_wholeslide_flawed_` sliding-window set) with
1,172 / 444 / 3,360 images — none matches the recorded 40x shape of 1,244 + 1,244, and
none is in the layout `corpus_manifest()` reads.

**The git repository is not a recovery source.** `placenta_BACKUP/.git` is a gitdir
pointer to `~/git-repos/placenta_BACKUP.git`, whose `refs/heads/main` tracks 70,306 files
including `tiles_v3/`. It preserves **exactly the same gap**: 434 tracked files under
`training_data_20x/positives/labels/`, and **zero** under `training_data_40x/`. The
corpus commit (`aa78c827`, "Add placental vessel WSI detection corpus …") is dated
2026-07-26 21:34 — about ten hours *after* the copy aborted at 11:27:44 — so git captured
the truncated working tree rather than preserving the original. Its `_done/` markers are
tracked in full (44 of them), which is consistent: the markers copied, the 40x tiles never
did.

**Conclusion: the v3 40x corpus and the 1,109 missing 20x labels are not on either mounted
volume, and not in the git repository.** Per §9b they were never copied here, and per the 44 `_done` markers they did
exist on the source machine.

**Where to look, in order of likelihood:**

1. **`D:\placenta_BACKUP\tiles_v3` on the Windows machine** — `backup.py`'s `DEST_ROOT`.
   This is almost certainly what was copied *from* on 2026-07-26; the copy aborted, but
   the source would be untouched.
2. **`C:\placenta_ssd\tiles_v3` on the Windows machine** — `backup.py`'s `SRC_TILES`, the
   live corpus the runs actually read. The `baseline` run read 5,303 + 489 = 5,792 images
   on 2026-07-13, which is the full study corpus, so it was intact then.
3. Any other external drive or NAS not currently mounted.

**When you reach a candidate, verify before trusting it:** run `backup.py --verify` (on
Windows, where its hard-coded paths resolve) and confirm all eight hashes against
`results/corpus_checksums.json`, in particular `40x/positives = d6b25b92a4c9b282` and
`40x/negatives = ed2f18c5a30ab909`.

**Run the unmodified `backup.py` there — not a reimplementation.** The AppleDouble filter
described above was necessary on macOS only: exFAT-hosted copies carry `._`-prefixed
sidecar files that `os.listdir` returns and that `corpus_manifest()`, written for Windows,
was never designed to skip. Without the filter every count doubles and every hash
mismatches. On Windows no such files exist, so the original code is correct as written and
is the authority.

Note that `training_data_5x` being absent is expected and harmless — 5x was excluded from
the study by design (`STUDY_SCALES = ("10x","20x","40x")`).

---

## 19. Content-integrity proof — round 2

Re-verified across both the repository and the slide destination, before and after every
round-2 move:

```
baseline : 708 files
after    : 708 files
multiset of SHA-256 digests: IDENTICAL
```

Files moved in round 2 — `slides_clean.yaml` (repo → `rigor/`),
`prepare_training_tiles.py` (`_EXCLUDED_FROM_RELEASE/` → `rigor/`), and
`figure_crops/crop_manifest.json` plus one gallery manifest (repo → SSD) — all carry
unchanged digests. No `.py`, `.yaml` or `.json` byte was modified in either round.

**Left untouched by design.** No `git init`, no staging, no commit. Nothing deleted.
