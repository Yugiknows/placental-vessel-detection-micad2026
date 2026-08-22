# Auditing and hardening a whole slide corpus for placental vessel detection

Code for the MICAD 2026 paper *Fabricated Ground Truth Corrupts the Score, Not the Model:
Auditing and Hardening a Whole Slide Corpus for Placental Vessel Detection*.

Yugesh Sarikonda, Umamaheswari Gurusamy, Divya Ravikumar, Sai Mounya Dumpala.
Springer Lecture Notes in Electrical Engineering. DOI: TODO on publication.

---

## The two branches

**You are on `portable`. Check this branch out to run the code.**

| branch | what it is |
|---|---|
| `main` | Every file byte-identical to what produced the published results. The runs predate version control, so there is no commit hash tying source to results; byte-identity against the archived manifests is the whole provenance argument, and editing anything would end it. `main` is the archival record and is not meant to be run. |
| `portable` | `main`, plus `rigor/paths.py`, plus the narrowest possible edit to 25 modules so the machine-specific roots come from the environment instead of being hard coded. Nothing else differs. |

`git diff main..portable` is therefore a precise record of exactly what was machine
specific about this code — 49 path literals in 25 modules, and nothing else.

`rigor/paths.py` resolves five roots, each from an environment variable falling back to
the original Windows value. With no environment set, on Windows, every resolved string is
identical to the literal on `main`, so behaviour there is unchanged. To run elsewhere:

```bash
export PLACENTA_SSD_ROOT=/path/to/placenta_ssd          # tiles_v3, ablations, screener, logs
export PLACENTA_SLIDES_ROOT=/path/to/PLACENTA_SLIDES    # the .ndpi/.ndpa slide drive
export PLACENTA_BACKUP_ROOT=/path/to/placenta_BACKUP    # backup.py's DEST_ROOT
export PLACENTA_MIGRATION_ROOT=/path/to/windows_gpu_migration
export PLACENTA_REPO_ROOT=/path/to/this/checkout        # <REPO> in the archived args.yaml

python rigor/paths.py    # print the resolved values for the current environment
```

---

## What this is

We set out to train a blood vessel detector on H&E stained placental whole slide images.
Before training we audited the corpus we had inherited, and found it could not support an
honest evaluation. This repository is the pipeline we built to fix that, plus the code and
archived records for the ablations that priced each defect.

There is no new model architecture here. The contribution is a procedure for establishing
that a corpus is fit to train and evaluate on, and five assertions that stop a run when it
is not.

## The three defects this code was written to catch

**1. Fabricated ground truth.** An inference script wrote model predictions back into the
pathologist's `.ndpa` annotation files and overwrote real annotations on five slides. File
timestamps settled the question of whether it mattered: the machine written files date from
2026-06-16 to 2026-06-29 and tiles were extracted between 2026-07-01 and 2026-07-03, so the
invented boxes were baked into the training labels. On one slide a surviving backup holds 39
genuine annotations where the extraction log records 143. Fold 0's 10x validation set was 70%
tiles from a slide whose every annotation was fabricated, so its reported 0.705 and 0.780
mAP50 graded a model against a copy of its own output.

The existing contamination guard missed all of it. It flagged a file only when *every*
annotation carried a `<predict>` tag, and it returned clean on parse errors and empty files.
Against eight known machine written files it passed two as clean, one containing 1,968
untagged machine boxes. `contamination_audit.py` is the replacement, and it fails closed: a
file is contaminated if it trips any signal, and a parse failure raises the flag rather than
clearing it.

**2. Tiling that destroyed scale consistency.** The prior sliding window tiler left the
target vessel's box touching the tile edge in 58% of positive tiles, and admitted a tile as
positive on as little as a 10% sliver of a vessel, then drew the box around the sliver. The
10x size gate had no upper bound, so 30 of 2,178 annotated vessels were silently clipped or
dropped. `tiling_config.py` and the vessel centered tiler replace it, adding a snugness
constraint (`SNUG_FRAC = 0.8`) that assigns a vessel to a magnification only if the whole
vessel plus context fits, and a raised visibility floor (`MIN_VISIBLE_FRAC = 0.35`, up from
0.10). Edge clipping falls from 57.9% to 16.1% at 10x against a hand curated reference at
17.9%, and mean off center displacement of the target drops from about 0.37 to zero.

**3. Negatives that were not background.** The pathologist annotated a subset of vessels, so
an unannotated tile was never proof that no vessel was there. Screening the initial negative
set put the contaminated fraction between 30% and 48%. For a detection task this is label
noise in the worst place: a visible vessel in a tile labeled background teaches the detector
that a vessel is not a vessel.

Two bugs in building the screen are worth reading `regen_negatives.py` for, because they
share a failure mode. The first screener handed NumPy arrays to a detector that reads BGR,
and the channel swap flattened H&E contrast so the screen returned zero detections while
reporting success. The second used the only pre contamination model available, which reached
78% to 92% recall and filed its own missed vessels as clean background. **From its output
alone, a screener that detects nothing looks exactly like a screener with nothing to
reject.** The working screen takes the union of two independent detectors under test time
augmentation at confidence 0.01, refuses to run unless that union first recovers 95% of known
positive tiles (measured: 100%, 90/90), and rejected 43,486 candidates against 124 under the
broken blind model. That 350-fold gap is the size of the bug.

## What the ablations found

`runs/` holds the archived manifest, args, final metrics, and per epoch CSV for all eight
runs. `results/results.json` is the aggregate. Held out slide `BFD_1`, 489 evaluation tiles,
one detector across all magnifications, seed 0.

| factor | condition | mAP50 |
|---|---|---|
| tiling | vessel centered (ours) | 0.890 |
| tiling | sliding window (prior) | 0.871 |
| negatives | screened (ours) | 0.890 |
| negatives | blind, count matched | 0.868 |
| fabrication | clean labels | 0.890 |
| fabrication | fabricated labels (paired swap, 8.6%) | 0.892 |

The fabrication row is the counterintuitive one and the reason for the paper's title.
Swapping 8.6% of training labels for machine written ones moved mAP50 from 0.890 to 0.892,
which is a null. **The damage did not land on what the network learned. It landed on the
score.** One fixed set of weights, with no retraining in between, scored 0.882 against
authentic labels and 0.124 against fabricated ones. Weights raised mostly on fabricated data
invert it, 0.194 against real and 0.457 against fabricated, reproducing the errors of the
model that wrote them. That self consistency is what inflated the pre audit fold to 0.705.

This is the label provenance stress test: score one set of weights against two label sets in
a single inference pass, with no retraining. A gap says at least one label set is not what it
claims to be. It does not say which, and it cannot. Our own case shows the division of labor:
the gap flagged the anomaly, file timestamps and a surviving backup identified which set was
fabricated, and a pathologist redrew the affected slides.

## The five constraints

Every defect above came from a convention that was written down and never enforced. These
now halt the pipeline rather than warn.

| constraint | enforces | defined in |
|---|---|---|
| C1 | no slide in both train and eval, checked against the image paths the framework actually loaded rather than the config | `ablations.py` |
| C2 | the clean slide list is hardcoded; a missing slide aborts the loader instead of returning an unverified set | `slide_registry.py` |
| C3 | every run is stamped with tiling hash `7b191fa9e02e`, and results across hashes cannot be combined | `ablations.py` |
| C4 | leave one slide out validation over eleven folds, average precision per slide as the metric | `loso_v3.py` |
| C5 | three seeds per grid cell in the run manifest | `run_manifest.py` |

C1 earned its place immediately: it caught a filter bug that had put every slide on both
sides of the split.

Slide count is not incidental to C4. Significance is assessed with an exact two sided
Wilcoxon signed rank test over per slide average precision, so the achievable p-value is
bounded by slide count alone whatever the effect size. At five slides the floor is 0.0625,
which puts p < 0.05 out of reach arithmetically. At seven it is 0.0156, at eleven it is 0.001.
Recovering three slides in the audit is the difference between a study that can reach
significance and one that cannot.

## Repository layout

```
rigor/       the pipeline: tiling, fingerprinting, contamination audit, negative
             screening, per tile provenance, and the ablation driver
             slides_clean.yaml is the frozen 11 slide allow list (C2)
runs/        eight run directories, each with manifest.json, args.yaml,
             metrics_final.json, results.csv
results/     results.json, corpus_checksums.json, verification.md,
             RESEARCH_LOG.md, RUN_QUEUE.md, plots/
docs/        archived handoff records
RELEASE_AUDIT.md   full inventory and the provenance argument for every module
```

Verification entry points:

```
python rigor/tiling_fingerprint.py             # recompute the corpus hash
python rigor/backup.py --verify                # check label checksums
python rigor/contamination_audit.py DIR [DIR2 ...]   # audit .ndpa files under a directory
```

The audit tool takes **directories**, not file paths. It walks each root looking for
`.ndpa` files, so handing it a single file audits nothing, reports success, and exits 0.
`docs/RELEASE_README.md` shows a single file path instead; it is preserved unaltered as a
historical record, and this line is the correct invocation.

Environment: Python 3.12.10, ultralytics 8.4.91. See `requirements.txt`.

## About the files in docs/

`release_tree.txt` and `release_manifest.md` were written by `build_handoff.py` when the
original handoff bundle was assembled. They are a record of that bundle, not a table of
contents for this repository, and they describe a seven file subset while this repository
ships the full pipeline. They are preserved unaltered because `release_tree.txt` records the
byte size that identified which copy of `tiling_config.py` produced the published results,
so correcting it would remove the evidence it exists to supply. `RELEASE_AUDIT.md` has the
current inventory.

## Provenance of this code

The runs predate version control in this project, so no commit hash ties source to results.
Authenticity was established by matching recorded constants, the corpus hash payload, and
file timestamps against the eight archived run manifests. All eight agree on the tiling hash,
the tiling method, the held out slide, the architecture, and the environment.

One gap is worth stating rather than leaving to be discovered. `run_ablations.py` has an mtime
54 seconds before the last run's manifest was written and after the other seven runs had
finished. It is provably the version that ran the final run and it is the only copy in
existence, but what changed before it is unrecoverable.

## Known limitations of this release

1. **`prepare_training_tiles.py` is not included.** This is a deliberate exclusion, not an
   oversight: it hard codes specimen identifiers for slides outside the ratified corpus.
   Seven modules import it and will not run without it: `tile_vessel_centered.py`,
   `regen_negatives.py`, `retile_clean.py`, `parallel_retile.py`,
   `build_blind_negatives.py`, `topup_5x_negatives.py`, `annotation_scale_report.py`. It is
   available on request through the same channel as the corpus.
2. **`MIN_ANN_OVERLAP = 0.10`**, cited in the paper's account of the tiling defect, is
   defined in that excluded file. Under the prior tiler a tile counted as positive when it
   contained as little as a 10% sliver of an annotated vessel, and the label box was drawn
   around the sliver. Compare `MIN_VISIBLE_FRAC = 0.35` in the vessel centered tiler.
3. **C3 verification is unaffected** by that exclusion. The chain `tiling_config.py` to
   `tiling_fingerprint.py` to `assert_c3()` does not touch it.
4. **The machine-specific paths are configurable on this branch, and hard coded on
   `main`.** The 25 modules enumerated in `RELEASE_AUDIT.md` read their roots from
   `rigor/paths.py` here; on `main` the same 25 carry the original Windows literals and
   will not run unmodified elsewhere. Setting no environment variable reproduces the
   original Windows paths exactly.
5. **The corpus is not in this repository.** See below.
6. **The 264 cell grid was never run.** It is specified in the paper (2x2x3 over
   architecture, mosaic, and seed, under leave one slide out across 11 folds, roughly 38 GPU
   days at the measured 104 s per epoch). The paper reports the epoch ceiling pilot and
   frames the ablations here as preliminary validation of the auditing framework rather than
   settled effect sizes.

## Data availability

The whole slide images are patient specimens. Consent covers the research reported in the
paper, not public deposition, so neither the slides nor the pathologist annotations are in
this repository and neither will be published.

The ratified corpus is 5,792 hand verified tiles across three magnifications: 753 positive
and 253 negative at 10x, 1,543 and 755 at 20x, 1,244 and 1,244 at 40x. `corpus_checksums.json`
carries the per scale label hashes.

A 5x scale was tiled for the production pipeline but excluded from the study
(`ablations.py`: `STUDY_SCALES = ("10x","20x","40x")`). The reason is statistical rather than
technical: two slides contain no 5x tiles at all, which leaves average precision undefined
for those folds and breaks the paired test. The scale is thin everywhere, at 54 positive and
59 negative tiles across all 11 slides.

Requests for access to the verified tiles are reviewed by the data governance office of PSG
Institute of Medical Sciences and Research, which releases what it holds under a data sharing
agreement.

## A note on what the audit does not cover

The corpus was 11 slides and the ablations use a single seed, so the numbers above give
direction and rough magnitude rather than effect sizes with a variance. The fabrication null
is claimed at the dose audited, on this corpus, at one seed, and is not evidence that label
corruption is harmless to training in general. Where that tolerance breaks down is an open
question and would need a dose series to answer.

## License

MIT, for the code in this repository. It does not extend to the imaging data, which is not
distributed here.

## Citation

See `CITATION.cff`. The DOI is assigned at publication.
