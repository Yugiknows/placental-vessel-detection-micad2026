# Handoff index — placental vessel detection ablation suite + epoch-cap pilot

For the writer agent. This folder is self-contained: every number traces to a file
below, no absolute local paths or credentials are present, and no LaTeX/prose/figures
for publication are included (brief §3.6) — that is your job, not this handoff's.

**Read `results.json` first** — it is the machine-readable summary and links to
everything else. **Read `RESEARCH_LOG.md` and `verification.md` before quoting any
single number** — several results contradict the brief's original expectations (§2),
and those corrections are the most important content in this handoff.

## Status

**All 8 planned runs complete.** The 264-cell grid was **not** run (brief §0.1).

| # | run | mAP50 | mAP50-95 | precision | recall |
|---|---|---|---|---|---|
| 1 | `baseline` | 0.890 | 0.610 | 0.893 | 0.811 |
| 2 | `A_contam_matched` | 0.892 | 0.615 | 0.845 | 0.789 |
| 3 | `A_contam_asitwas` | 0.891 | 0.613 | 0.857 | 0.835 |
| 4 | `A_contam_fabval` | 0.882 | 0.599 | 0.906 | 0.765 |
| 5 | `A_contam_heavy` | 0.194 | 0.036 | 0.268 | 0.345 |
| 6 | `B_sliding_window` | 0.871 | 0.599 | 0.860 | 0.779 |
| 7 | `C_blind_negatives` | 0.868 | 0.602 | 0.857 | 0.786 |
| 8 | `pilot_mosaic1` | 0.867 | 0.587 | 0.839 | 0.792 |

All evaluated on the same honest held-out slide, `BFD_1` (489 tiles) — chosen because it
is real, hand-verified, never fabricated, never recovered. Runs 4/5 additionally carry a
second evaluation on held-out fabricated tiles (see below and `results.json` →
`ablations.A_fabrication.*.fabricated_val`).

## What to read, in order

1. **`results.json`** — machine-readable results in the brief's §3.1 schema, plus
   `epoch_cap_pilot` and `notes`. Every field traces to a file in `runs/`.
2. **`verification.md`** — item-by-item confirmation/correction of every §2 claim the
   runs touch (V1–V10). **Read V9 before citing anything about fabrication** — the
   brief's expected "contaminated training collapses on the honest slide" story does
   **not** hold at realistic contamination doses; the true mechanism (self-consistency
   / evaluation inflation) only appears once fabrication dominates training, and even
   then the magnitude is confounded by a smaller training set. This is the single most
   important correction in this handoff.
3. **`RUN_QUEUE.md`** — the same 8 results with a plain-language findings summary per
   ablation and the 6 cross-cutting limitations that must reach the paper.
4. **`RESEARCH_LOG.md`** — full lab notebook, 20 dated entries. Includes bugs found and
   fixed mid-suite (a silent two-process race that could have corrupted a run; an OOM
   caused by training multiple models in one process; a run that was built but never
   wired into the orchestrator) and my own corrected overclaims (an initial 94%
   negative-contamination estimate that turned out to be the recall-maximising extreme
   of a 30–48% range). Nothing here has been quietly retracted — corrections sit next
   to the original claim.
5. **`plots/`** — 5 QC plots (sanity checks, not publication figures): per-ablation bar
   charts (A/B/C), the full convergence-curve overlay, and the inflation direction-flip
   comparison (`A_contam_fabval` vs `A_contam_heavy`).
6. **`runs/<name>/`** — per-run evidence for all 8 runs: `manifest.json` (config, seed,
   tiling hash, exact train/val slide lists, git commit, dataset yaml, Ultralytics
   version), `results.csv` (raw per-epoch metrics, unedited), `args.yaml` (resolved
   training config — path fields sanitised to `<DATA>`/`<REPO>` placeholders),
   `metrics_final.json` (headline metrics + epoch each was measured at, and
   `fabricated_val` where applicable).
7. **`RELEASE_README.md` + `release_tree.txt` + `release_manifest.md` +
   `corpus_checksums.json`** — the brief §1c/§3.5 FAIR release inventory: which files
   constitute the reproducibility bundle (allow-list, tiling-hash code, checksums,
   fail-closed contamination guard, negative-mining screen) and what each one does.

## The three findings likely to matter most for the paper

1. **Low/moderate fabrication dose (8.6–24% of tiles) does not measurably harm
   honest-slide detection AP**, at n=1 seed. This contradicts the brief's premise that
   contamination "collapses" performance. (`verification.md` V9, Finding 1.)
2. **The self-consistency/inflation mechanism is real but conditional**: it only
   appears once training is fabrication-*dominated*, not merely fabrication-*present*.
   `A_contam_fabval` (clean-dominated) and `A_contam_heavy` (fabrication-dominated)
   show opposite-sign fabricated-vs-honest deltas (−0.757 vs +0.263). The magnitude of
   `A_contam_heavy`'s absolute scores is confounded by a much smaller training set — the
   **direction** of the flip is the reliable finding, not the specific numbers.
   (`verification.md` V9, Finding 2.)
3. **The epoch cap for a future grid must come from the mosaic=1 arm** (confirmed:
   converges at ~2× the epochs of mosaic=0 — ep37 vs ep19 best-fitness). Recommended
   cap: patience=60 with a 120-epoch ceiling. Projected full-grid cost at that cap:
   ~38 GPU-days on one RTX 4060 — the concrete number behind brief §0.1's instruction
   not to run the grid now. (`verification.md` V8.)

## Limitations (also see `RUN_QUEUE.md` and `verification.md` "Deviations from the brief")

- One seed per condition throughout (brief-permitted); deltas of ~0.02 should not be
  read as distinguishable from run-to-run noise on that basis alone.
- The screened negatives' "0% contaminated" measurement is circular (the set was built
  by rejecting what the same model flagged); the independent check was human labelImg
  review, not the automated re-audit.
- We do not reproduce the original leaked 0.705/0.780 scores — the source `.ndpa`
  generation used for that leaked run is unknown, and at least 4 differently-generated
  copies of the relevant slide's annotations exist on disk.
- `A_contam_asitwas` and `A_contam_heavy` both carry a training-set-size confound
  relative to `baseline` (different slide/tile counts) — the causal claims for
  fabrication rest on `A_contam_matched` (perfectly matched slides/tiler/negatives).

## Explicitly not included (brief §3.6 / §4)

No paper sections, titles, abstract, publication-styled figures, or reference list.
No 264-cell grid results (not run). No claim that the architecture × mosaic interaction
hypothesis is supported (not tested by this suite). The leaked 0.705/0.780 scores appear
only as the contaminated "before" contrast, never presented as valid.
