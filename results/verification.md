# Verification of §2 claims

For each claim the runs touch: **confirmed** or **corrected**, with the evidence.
Nothing here is from memory — every value traces to a command in this repo.

Status key: ✅ confirmed · ⚠️ corrected/refined · ⏳ pending (run not yet complete)

**All 8 planned runs are now complete** (6 ablation conditions + 2 pilot arms, plus the
additional `A_contam_heavy` run added mid-suite — see V9). No `⏳ pending` items remain
below; every one has been resolved to a final, logged number.

---

## V1. Corpus identity (C3 gate) — ✅ confirmed

| | |
|---|---|
| Required by brief | `7b191fa9e02e` |
| Corpus hashes to | `7b191fa9e02e` |
| Method | `vessel_centered_v3` |
| Study tiles (10×/20×/40×) | **5,792** (10× 753+253, 20× 1543+755, 40× 1244+1244) |
| 5× | excluded from every study/ablation result |

Command: `python rigor/tiling_fingerprint.py`; gate in
`rigor/ablations.py::assert_c3()` — **aborts any run** whose corpus hash differs.

> Note: `tiling_config.py` was edited after the manifest was written (screening
> parameters were added), so this needed re-checking rather than assuming. It still
> matches, because the hash covers tiling geometry + slide list + tile corpus.

---

## V2. Held-out slide choice — recorded

**`BFD_1`**, chosen from data, not preference:

- **Originally clean** — never fabricated, never recovered (so it cannot flatter
  either side of ablation A).
- **334 eval positives**, vessels at all three scales (10× 37 / 20× 162 / 40× 135).
- Rejected `S.2_723_26_A3_FD_1` despite having far more eval tiles (1,517): it is
  **43% of the entire corpus**, so holding it out would cripple training and
  confound every comparison.
- Rejected `A2FD_1` (172 eval tiles): viable, but ~half the eval data, and with
  **one seed per cell** metric stability matters.

Eligibility table: `python rigor/ablations.py` (see also §V2 table in results.json).

---

## V3. Negative-tile contamination (premise of ablation C) — ✅ confirmed, refined

The brief says **≈35%** of first-pass "background" tiles held real vessels.
**Confirmed, and now bracketed properly.**

Measured with the high-recall screener (trained on hand-reviewed positives),
with TTA, across confidence thresholds. The **positives column is the calibration
control** — it shows the detector is not simply over-firing:

| conf | POSITIVES (control) | BLIND negatives | SCREENED negatives |
|---|---|---|---|
| 0.01 | 100% | 94% | 0% |
| 0.05 | 100% | 81% | 0% |
| 0.10 | 100% | 70% | 0% |
| 0.25 | 100% | **48%** | 0% |
| 0.50 | 99% | **30%** | 0% |

**Honest figure: ~30–48% of blind negatives contain a real vessel.** The brief's
≈35% sits inside that range. Even at conf=0.50 — conservative, high-precision, and
still detecting 99% of tiles known to contain vessels — **30%** of blind negatives
hold a vessel.

We report the range, not the alarming 94%: conf=0.01 maximises recall and
over-flags by design.

### ⚠️ Important caveat — the "0%" for screened negatives is NOT independent

The screened set was **constructed by rejecting** anything this same model flagged
at conf 0.01. Its 0% is therefore **true by construction**, not independent
validation. The genuine independent check was the **human labelImg review** of every
surviving tile. Do not present the 0% as an unbiased measurement.

Sample: 200 tiles per set, seeded (`random.Random(2)`), 10×/20×/40× pooled.

---

## V4. Fabrication dose (premise of ablation A) — ✅ confirmed, quantified

Machine-written `.ndpa` re-tiled with the **identical** `vessel_centered_v3` method,
so ablation A varies labels only.

| slide | fabricated positive tiles |
|---|---|
| `S.3152_26_A3FD_1` | 519 |
| `A2FD_1_S.2058_26` | 338 |
| `S.2723_26_A2_FD_1` | 121 |
| `A3_FD_1` | 104 |
| `S.2016_26_A3_FD_1` | 49 |
| **total** | **1,131** |

Against 3,540 real study positives, the pre-audit corpus was **≈24% fabricated** —
a substantial dose, not a rounding error.

**Two slides have BOTH a clean and a fabricated `.ndpa`** (`A2FD_1_S.2058_26`,
`S.2723_26_A2_FD_1` — 459 tiles). These enable a **controlled label swap**: identical
slides, identical tiler, identical tiles; only the boxes differ. `A_contam_matched`
therefore attributes any gap to fabrication *alone*.

`A_contam_asitwas` reconstructs the pre-audit corpus (5 fabricated slides) for the
realistic magnitude, but has **3 more training slides** than the clean condition
(the permanently-lost slides were later dropped). **That is a confound and is
reported as one** — the causal claim rests on `A_contam_matched`.

Build: `python rigor/build_contaminated.py`

---

## V5. Tiling edge-clip effect — ✅ confirmed, quantified

Geometry (`python rigor/validate_tiles.py --compare`):

| scale | sliding window | hand-curated ref | vessel-centred (ours) |
|---|---|---|---|
| 10× | 57.9% | 17.9% | 16.1% |
| 20× | 51.7% | 9.0% | 13.5% |
| 40× | 53.2% | 7.4% | 11.2% |

(% of positive tiles whose vessel box touches the tile border.)

**AP/recall cost, measured by `B_sliding_window` vs `baseline`** (identical held-out
`BFD_1` eval; negatives held constant/screened both sides; ONLY the positive-tile
source differs — sliding-window vs vessel-centred):

| condition | mAP50 | mAP50-95 | precision | recall | epochs |
|---|---|---|---|---|---|
| vessel-centred (`baseline`) | 0.890 | 0.610 | 0.893 | 0.811 | 79 |
| sliding-window (`B_sliding_window`) | 0.871 | 0.599 | 0.860 | 0.779 | 96 |
| **Δ (sliding − vessel-centred)** | **−0.020** | −0.011 | −0.033 | **−0.033** |

**Real but modest** — far smaller than the 58%→16% edge-clip swing alone might suggest.
Precision and recall drop by essentially the **same** amount (−0.0332 vs −0.0325) — this
does *not* show recall being selectively harmed; both false negatives and false
positives increase roughly together. Confirmed the brief's expected *direction*
(edge-clipping costs AP); the brief's expectation of a recall-*specific* penalty is
**not distinctly supported** — the effect looks like a general quality degradation, not
a recall-selective one.

Manifests: `runs/baseline/manifest.json`, `runs/B_sliding_window/manifest.json`.
Raw curves: `runs/B_sliding_window/results.csv`.

---

## V6. Trial numbers (0.731 / 0.384 / 0.82 / 0.55) — ⚠️ neither confirmed nor superseded (different held-out slide)

Those came from **fold 0, held-out `A2FD_1`**. The ablation suite fixes a *different*
honest held-out slide (`BFD_1`, chosen for 2× the eval data), so the ablation baseline
is **not directly comparable** to the trial and does not "re-confirm" it.

Both are reported: the trial as a separate logged run on `A2FD_1`, the ablation
baseline on `BFD_1`. Neither supersedes the other; they are different held-out slides.

Trial run (already complete, honest, C1-compliant):
`single_allmag`, fold 0, mosaic=0, seed 0 →
mAP50 **0.731** @ ep50 · mAP50-95 **0.384** @ ep29 · P **0.82** / R **0.55** ·
early-stopped ep 89 · **134 s/epoch** on RTX 4060.

> Subtlety worth recording: Ultralytics counts `patience` from best **fitness**
> (mAP50-95), not mAP50. Best fitness was epoch 29; 29 + 60 = 89, which is exactly
> where it stopped. mAP50 and mAP50-95 peaked **21 epochs apart** — so "converged at
> epoch N" depends on which metric you ask, and a cap set on the wrong one would
> silently truncate runs.

---

## V7. s/epoch on this hardware — ✅ confirmed

**134 s/epoch**, RTX 4060, `single_allmag`, imgsz=1024, batch=16, AMP on.

Measured, not projected. GPU sat at **96% utilisation with 4.6 GB of 8 GB VRAM** —
i.e. **compute-bound, not data-starved**. Raising batch 8→16 changed epoch time by
~1% (73 s → 72 s on the screener), so batch size and worker count are **not** levers
on this workload. AMP was already enabled by default.

Grid projection (future work only — **the grid was not run**):

| epoch cap | 264 trainings, one RTX 4060 |
|---|---|
| 60 | ~12 days |
| 100 | ~20 days |
| 300 | ~61 days |

---

## V8. Epoch cap — ✅ confirmed (pilot complete)

Both arms run on the same fold/slides as `baseline` (mosaic=0 = `baseline` itself;
mosaic=1 = `pilot_mosaic1`), one seed, patience=60. Ultralytics counts patience from
best **fitness** (mAP50-95), not mAP50 — the two can peak >20 epochs apart (see V6),
so fitness is the correct epoch to read for convergence.

| arm | best mAP50 | best fitness (mAP50-95) | ran to | still improving at end? |
|---|---|---|---|---|
| mosaic=0 (`baseline`) | 0.890 @ ep17 | 0.610 @ **ep19** | 79 | No |
| mosaic=1 (`pilot_mosaic1`) | 0.867 @ ep9 | 0.587 @ **ep37** | 97 | No |

**Neither arm was still improving when it stopped** (both caught naturally by
patience=60), so a cap recommendation is valid — the pilot's refusal condition
(brief §1b) does not trigger.

**Mosaic=1 converges ~2× later than mosaic=0** (ep37 vs ep19 fitness) — confirms the
brief's expected asymmetry. Had a cap been read from mosaic=0 alone, it would have
truncated mosaic=1 well before its true peak.

**Recommended cap (taken from the slower, mosaic=1, arm):** keep `patience=60`
(already adaptive per run) with a fixed ceiling of **120 epochs** — margin above
mosaic=1's natural stop at ep97, since other folds/seeds in a future grid may converge
slightly later than this single-fold measurement. This is **n=1 fold/seed**; it has not
been validated across the other 10 LOSO folds.

**Wall-clock:** ~100–108 s/epoch on this hardware (RTX 4060). Projected full 264-run
grid at ceiling=120: **~38 GPU-days on one RTX 4060** — confirms brief §0.1's
instruction not to run the grid on the current deadline/hardware.

> `close_mosaic=10` (an Ultralytics default) disables mosaic for the final 10 epochs,
> so the mosaic arm is **not purely mosaic**. This biases *conservatively* — against
> the hypothesis — but must be stated whenever the grid is eventually reported.

Manifests: `runs/baseline/manifest.json`, `runs/pilot_mosaic1/manifest.json`.
Raw curves: `runs/baseline/results.csv`, `runs/pilot_mosaic1/results.csv`.
Full computation: `handoff/results.json` → `epoch_cap_pilot`.

---

## V9. Contaminated-vs-clean gap — ⚠️ CORRECTED (brief's expected story is backwards for a clean-dominated model; confirmed only once fabrication dominates training)

Brief §1a's expected story: *"contaminated training scores high on its own fabricated
validation but collapses on the honest slide."* Four runs test this at increasing
fabrication dose. All share the same honest eval slide (`BFD_1`); two also carry a
second, held-out-fabricated evaluation.

| run | training composition | honest mAP50 | honest R | fabricated-eval mAP50 | fabricated-eval R |
|---|---|---|---|---|---|
| `baseline` | 100% clean (10 slides) | 0.890 | 0.811 | — | — |
| `A_contam_matched` | 8.6% fabricated (causal, paired swap) | 0.892 | 0.789 | — | — |
| `A_contam_asitwas` | 24% fabricated (confounded, +3 slides) | 0.891 | 0.835 | — | — |
| `A_contam_fabval` | clean-**dominated** (4 fabricated / 10 total slides) | 0.882 | 0.765 | **0.124** | 0.245 |
| `A_contam_heavy` | fabrication-**dominated** (4 fabricated slides ONLY, 1,224 tiles) | 0.194 | 0.345 | **0.457** | 0.454 |

**Finding 1 — low/moderate fabrication dose does not measurably harm honest-slide AP.**
`A_contam_matched` (causal, paired label swap, 8.6% of tiles) and `A_contam_asitwas`
(24%, confounded by +3 slides) both land within noise of `baseline` on the honest slide.
The fabricated boxes came from a *working* detector (194 vs 200 real boxes on one
slide, 77 vs 27 on the other) — a degraded copy of the truth, not random noise — so a
model trained on a *minority* of such labels is not measurably worse at real detection.
⚠️ **This contradicts the brief's premise that contamination "collapses" honest-slide
performance at these doses** — it does not, at n=1 seed, at 8.6–24% contamination.

**Finding 2 — the brief's collapse/inflation story is backwards for a clean-dominated
model, and only appears once fabrication DOMINATES training.**
`A_contam_fabval` (clean-dominated, i.e. what a normal training run with SOME
contamination looks like): honest **0.882** ≫ fabricated-eval **0.124**. The model
disagrees with the fabricated boxes (recall 0.245 → it does not "see" ~75% of them),
because it learned real vessel appearance from the clean majority of its training data.

`A_contam_heavy` (deliberately fabrication-dominated, added specifically to test the
brief's predicted direction): honest **0.194** ≪ fabricated-eval **0.457** — the sign
**flips**. When training is predominantly on one generator's invented boxes, the model
partially reproduces that generator's own errors and scores relatively better against
them than against reality — the self-consistency mechanism the brief's hypothesis
describes.

⚠️ **`A_contam_heavy`'s absolute numbers are confounded by training-set size**
(1,224 tiles / 4 slides vs 5,300+ tiles / 10+ slides for every other run) — its very low
honest score (0.194) reflects data volume as much as data quality, and should not be
read as "fabrication alone costs this much." The **within-model** fabricated-vs-honest
delta (+0.263, same trained weights, two eval sets) is **not** subject to that confound
and is the load-bearing number here.

**We do not reproduce the original leaked 0.705/0.780.** `S.3152_26_A3FD_1` has (at
least) four different machine-generated `.ndpa` on disk with different box counts
(301/131/146/298); the original leaked run's generation is unknown. Our controlled
numbers (0.124, 0.457) stand on their own, not as a replication.

**Net correction to brief §2/§1a:** the "collapse on the honest slide" framing is not
supported at realistic (8.6–24%) contamination in a single training run; the
**self-consistency / inflation** mechanism is real but requires fabrication to dominate
training, and even then the honest-slide *degradation* observed is confounded with a
much smaller training set in our design.

Builds/manifests: `rigor/build_contaminated.py`, `rigor/build_heavy.py`;
`runs/A_contam_fabval/manifest.json`, `runs/A_contam_heavy/manifest.json`
(`paired_label_swap` / `fabricated_val` fields carry full provenance).

---

## V10. Negative-noise effect on recall — ✅ confirmed, quantified (modest)

`C_blind_negatives` vs `baseline`: positives and total training-image count held
**identical** (5,303 both sides — blind negatives were subsampled to match the
screened count exactly, see RESEARCH_LOG L7); only negative *quality* differs.

| condition | mAP50 | mAP50-95 | precision | recall |
|---|---|---|---|---|
| screened negatives (`baseline`) | 0.890 | 0.610 | 0.893 | 0.811 |
| blind/unscreened negatives | 0.868 | 0.602 | 0.857 | 0.786 |
| **Δ (blind − screened)** | **−0.022** | −0.008 | −0.036 | **−0.025** |

**Recall drops by 0.025** — real, in the predicted direction (unscreened negatives,
~30–48% of which contain a real vessel, teach the model that visible vessels are
background) — but **modest**, smaller than the ~30–48% contamination rate alone might
suggest, and comparable in magnitude to precision's drop (−0.036). At one seed, a delta
of this size should be treated as suggestive rather than conclusive.

Training-curve stability (epochs ≥10): blind negatives had **lower** SD than screened
(0.032 vs 0.040) — this is a consistent downward shift across training, not the
instability collapse seen in the high-dose fabrication run (RESEARCH_LOG L14).

Manifests: `runs/baseline/manifest.json`, `runs/C_blind_negatives/manifest.json`.

---

## Deviations from the brief

- **The 264-cell grid was NOT run** and no grid results are reported (brief §0.1, upheld
  throughout).
- 5× excluded from every study/ablation number.
- One seed (0) per ablation cell, as permitted; stated as a limitation.
- **§1a's expected fabrication story did not hold as stated, and one unplanned run was
  added to resolve it.** The brief predicted contaminated training would score high on
  its own fabricated validation while collapsing honestly. At the doses tested first
  (`A_contam_matched` 8.6%, `A_contam_asitwas` 24%), honest-slide performance did **not**
  collapse. `A_contam_fabval` (clean-dominated) showed the *opposite* sign — fabricated
  eval scored far *below* honest eval. Only after adding `A_contam_heavy`
  (fabrication-dominated training, not in the original 6-run plan, agreed upon and
  logged) did the predicted sign appear. This is reported as a correction to §2, not
  papered over — see V9 for the full account, including the confound in
  `A_contam_heavy`'s absolute numbers.
- `B_sliding_window`'s recall-specific penalty (predicted in §1a) is **not distinctly
  supported** — precision and recall dropped by essentially equal amounts (see V5).
- We could not reproduce the original leaked 0.705/0.780 scores — the source `.ndpa`
  generation used for the original leaked run is unknown, and `S.3152_26_A3FD_1` alone
  has four different machine-generated `.ndpa` versions on disk with different box
  counts. Our fabricated-eval numbers (0.124, 0.457) are controlled results in their own
  right, not replications.
