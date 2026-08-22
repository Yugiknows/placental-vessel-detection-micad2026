# Release bundle — placental vessel detection corpus + rigor pipeline

Factual description of the FAIR release components (for the writer's "Data and Code
Availability" paragraph — this file is infrastructure documentation, not paper prose).

## What this bundle is

The ratified, hand-reviewed tile corpus (method `vessel_centered_v3`, tiling hash
`7b191fa9e02e`, 11 slides, 5,792 study tiles at 10x/20x/40x) used for every ablation run
in this handoff, plus the code that built and verified it.

## Components

| component | path | one-line purpose |
|---|---|---|
| Clean slide allow-list (C2) | `rigor/slides_clean.yaml` | frozen list of the 11 ratified slides; loader raises rather than falling back to "all slides" if missing |
| Tiling config | `rigor/tiling_config.py` | single source of truth for tile size, downsample, and per-scale size gates |
| Tiling-hash manifest | `rigor/tiling_fingerprint.py` | computes the corpus identity hash (`7b191fa9e02e`) from config + slide list + tile content; used to gate every training run (C3) |
| Per-file checksums | `rigor/backup.py` (writes `manifest.json` alongside the backup) | SHA-based label-content hash per scale/split, used to verify the corpus has not silently drifted |
| Fail-closed contamination guard | `rigor/contamination_audit.py` | detects machine-generated `.ndpa` (vs pathologist ground truth); replaces an earlier guard that passed 2/8 known-contaminated files as clean |
| Negative-mining screen | `rigor/regen_negatives.py` | builds screened negative tiles via a union of two detectors + TTA, because raw "no annotation overlap" negatives are ~30-48% contaminated with real, unlabelled vessels |
| Per-tile provenance ledger | `rigor/tile_provenance.py` | tracks per-tile (not per-slide) verification status, since contamination is a per-annotation property |

## How to verify the corpus

```
python rigor/tiling_fingerprint.py       # recompute the tiling hash
python rigor/backup.py --verify          # check the corpus against manifest.json checksums
python rigor/contamination_audit.py <path-to-.ndpa>   # audit a single annotation file
```

## Constraints enforced (see `rigor/ablations.py`, `rigor/run_ablations.py`)

- **C1** — no slide in both train and eval (checked against the image lists Ultralytics
  actually reads, not just intent)
- **C2** — frozen clean-slide allow-list only, no directory globbing
- **C3** — single tiling hash; training aborts on any mismatch
- **C4** — per-slide AP as the unit of analysis (used in the future full grid, not in
  this single-held-out-slide ablation suite)
- **C5** — ≥3 seeds per grid cell (future grid only; this ablation suite uses 1 seed
  per condition, stated as a limitation)

## What is NOT in this bundle

- The raw `.ndpi` whole-slide images and pathologist `.ndpa` annotations (large,
  potentially subject to data-use restrictions — not included here).
- The 264-cell grid (not run — see `handoff/RESEARCH_LOG.md` and brief §0.1).
