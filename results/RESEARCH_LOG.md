# Research Log

A running record of every observation, bug, correction and decision that could
affect a reported number. Appended continuously; not a summary — a lab notebook.

**Rule for this file:** if a finding contradicts something we previously believed,
the old belief stays in the record with the correction next to it. Nothing is
quietly overwritten.

Corpus under study: `vessel_centered_v3`, tiling hash `7b191fa9e02e`, 11 slides,
5,792 study tiles (10×/20×/40×; 5× excluded).

---

## 2026-07-13 — Ablation suite launched

### L1. C3 gate needed re-checking, not assuming
`tiling_config.py` was edited after `run_manifest.json` was written (negative-screening
parameters were added). The corpus hash still resolves to `7b191fa9e02e` — the hash
covers tiling geometry + slide list + tile corpus, and none of those changed. But this
was checked, not assumed. Gate: `ablations.py::assert_c3()`, aborts any run on mismatch.

### L2. Held-out slide: BFD_1 — and the trial is NOT comparable to it
Chose `BFD_1` (originally clean, never fabricated, never recovered; 334 eval positives
across all three scales).

Rejected `S.2_723_26_A3_FD_1` despite having 1,517 eval positives — it is **43% of the
entire corpus**, so holding it out would cripple training and confound every comparison.
Rejected `A2FD_1` (172 eval tiles): viable but ~half the eval data, and metric stability
matters at one seed.

**Consequence, and it is important:** the earlier trial used held-out `A2FD_1` and scored
mAP50 **0.731**. The ablation baseline uses held-out `BFD_1` and is scoring ~**0.89**.
These are the SAME architecture, corpus and settings — the difference is the slide.

> **They are not interchangeable, and neither validates the other.** Brief §3.3 asked us
> to "re-confirm or supersede" the trial numbers; that instruction assumed a shared
> held-out slide and cannot be honoured. Both are reported as independent held-out-slide
> checks. (Confirmed with the writer; §3.3 superseded.)

This also means the ablation **deltas** are valid (all six runs share `BFD_1`) but the
**absolute values are BFD_1-specific** and must not be generalised to "the model scores
0.89".

### L3. Negative contamination: my own first number was wrong — corrected
First measurement said **94%** of blind negatives contain a vessel. That used conf=0.01,
which is the recall-maximising threshold and **over-flags by design**. Reporting it would
have been cherry-picking the alarming end.

Re-measured across thresholds, with known-positive tiles as a **calibration control**:

| conf | POSITIVES (control) | BLIND neg | SCREENED neg |
|---|---|---|---|
| 0.01 | 100% | 94% | 0% |
| 0.05 | 100% | 81% | 0% |
| 0.10 | 100% | 70% | 0% |
| 0.25 | 100% | **48%** | 0% |
| 0.50 | 99% | **30%** | 0% |

The control column is what makes this trustworthy: at every threshold the detector still
finds ~100% of tiles that genuinely contain vessels, so it is not simply over-firing.

**Reported figure: ~30–48%.** Headline = the conservative 30% (conf=0.50, where the model
still recovers 99% of known positives). The 94% figure is **dropped**.
Brief's ≈35% → **confirmed**, sits inside the range.

### L4. CIRCULARITY — the screened set's "0% contaminated" is NOT evidence
The screened negatives were **constructed by rejecting** whatever this same model flagged
at conf=0.01. Their 0% contamination is therefore **true by construction**, not an
independent measurement.

The genuine independent check is the **human labelImg review** of every surviving tile.

> This must survive into the paper verbatim (negative-mining section *and* limitations).
> The paper's whole subject is a model being graded against its own output; we cannot
> commit a softer version of the same error and call it validation.

### L5. Fabrication dose quantified — 24% of the pre-audit corpus
Machine-written `.ndpa` re-tiled with the **identical** `vessel_centered_v3` method (so
ablation A varies labels only, not tiling).

| slide | fabricated positive tiles |
|---|---|
| `S.3152_26_A3FD_1` | 519 |
| `A2FD_1_S.2058_26` | 338 |
| `S.2723_26_A2_FD_1` | 121 |
| `A3_FD_1` | 104 |
| `S.2016_26_A3_FD_1` | 49 |
| **total** | **1,131** |

Against 3,540 real study positives → the pre-audit corpus was **≈24% machine-invented**.
Upgrades the fabrication claim from "≈100 boxes on one slide" (anecdote) to a
corpus-level result.

### L6. The 459-tile paired label swap — the causal engine
Two slides carry **both** a clean and a fabricated `.ndpa`:
`A2FD_1_S.2058_26` (clean 200 boxes / fabricated 194) and
`S.2723_26_A2_FD_1` (clean 27 / fabricated 77).

Tiled both ways: **clean = 404 tiles, fabricated = 459 tiles.**

`baseline` vs `A_contam_matched` therefore differ in **nothing but the label source** —
identical slide list, identical tiler, identical negatives. That makes it a controlled
experiment, not an observational contrast: it can support *causation*, not just
correlation.

Wrinkle, recorded honestly: the tile counts are not identical (404 vs 459) because the
fabricated `.ndpa` contains different boxes, so vessel-centred cropping yields different
crops. Unavoidable. It is a ~1% difference in a 5,300-image training set, against an
identical slide list/tiler/negative set.

Both `.ndpa` source paths + box counts + CLEAN/GENERATED verdicts are recorded in the
`manifest.json` of both runs.

### L7. CONFOUND CAUGHT — ablation C had 21% more training data
First build of `C_blind_negatives` came out at **6,412** training images vs baseline's
**5,303**.

Cause (itself a finding): blind negatives reach 1:1 with positives trivially, while
*screened* negatives fall short — **vessel-free placental tissue is genuinely rare**.
Left unfixed, ablation C would have varied negative **quantity** as well as **quality**,
and any recall drop could have been dismissed as a data-volume artefact.

**Fixed:** blind negatives subsampled to exactly the screened count per (slide, scale)
→ **2,097 negatives**. Both conditions now **5,303 training images**, identical slides,
identical positives. **Only negative quality varies.** Without this, ablation C could not
have supported a causal claim.

### L8. Biological finding: vessel-free placental tissue barely exists at low mag
Negative availability scaled inversely with tile size — we rejected 43,486 candidates to
keep 2,269:

| scale | tile covers (l0 px) | negatives found / needed |
|---|---|---|
| 40× | 1,024 | 100% |
| 20× | 2,048 | 49% |
| 10× | 4,096 | 35% |
| 5× | 16,384 | **4%** |

Placental villous tissue is so densely vascular that a large field with **no** vessel in
it is close to a contradiction in terms. At 5× we had to abandon thresholding entirely and
switch to *ranking* (keep the least vessel-like tiles available), then human-verify.

This is not a tooling artefact — it is a property of the tissue, and it explains why
"background" tiles in this domain are so easy to get wrong.

### L9. Ultralytics stops on FITNESS, not mAP50 — affects any epoch cap
In the trial, best **mAP50** was epoch 50; best **mAP50-95 (fitness)** was epoch 29.
Early stopping fired at 89 = 29 + 60 (patience). The two metrics peaked **21 epochs
apart**.

So "when did it converge?" has two different answers depending on which metric is asked,
and an epoch cap set on the wrong one would silently truncate runs. The pilot must report
both.

### L10. Hardware: compute-bound, not VRAM-bound — no free speed available
Measured during a live run: GPU **93% utilised** (min 81%), VRAM **6,080 / 8,188 MB**.

Raising batch 8→16 changed epoch time ~1% (73→72 s). AMP already on by default; workers
already 8. **Batch size, VRAM and worker count are not levers on this workload.** A second
concurrent job would need 4–6 GB against 2.1 GB free → OOM, and would kill the in-flight
run for ≤7% idle compute.

Measured throughput: RTX 4060 = 63.8 img/s; RTX 5060 Ti (remote) = 92.8 img/s (**1.45×**).
**134 s/epoch** for `single_allmag` at imgsz=1024, batch=16.

---

## Results as they land (held-out slide: BFD_1, 489 eval tiles, seed 0)

| run | mAP50 | mAP50-95 | P | R | epochs | s/ep |
|---|---|---|---|---|---|---|
| `baseline` (clean + vessel-centred + screened) | **0.890** | 0.610 | 0.893 | 0.811 | 79 | 100 |
| `A_contam_matched` | — | | | | | |
| `A_contam_asitwas` | — | | | | | |
| `B_sliding_window` | — | | | | | |
| `C_blind_negatives` | — | | | | | |
| `pilot_mosaic1` | — | | | | | |

### L11. Baseline is much stronger on BFD_1 than the trial was on A2FD_1
`baseline`: mAP50 **0.890**, mAP50-95 **0.610**, P 0.893, R 0.811 (79 epochs, 100 s/ep).
Trial (held-out `A2FD_1`): mAP50 0.731, mAP50-95 0.384, P 0.82, R 0.55.

Same architecture, same corpus, same hyperparameters, same seed. **The only difference is
which slide was held out.** mAP50-95 differs by 0.23 — a huge gap.

This is hard evidence for L2: **per-slide scores are not interchangeable.** Any single
held-out slide gives a number that is as much a property of *that slide* as of the model.
It is also the clearest possible argument for the eventual grid's design — per-slide AP
across 11 folds, tested pairwise (C4/C5) — because a single fold could tell almost any
story you wanted.

Practical note: also faster than expected — **100 s/epoch** (vs 134 s/epoch measured on
fold 0), because `BFD_1` holds out fewer training tiles than `A2FD_1` does.

### L12. RUN FAILURE — CUDA OOM on run 2 (my bug, not hardware)
`--run-all` trained all six models **inside one Python process**. Run 2
(`A_contam_matched`) died with `torch.AcceleratorError: CUDA error: out of memory`.

Root cause: **PyTorch does not fully release VRAM between successive Ultralytics
trainings in the same interpreter.** Allocations accumulate until the card is exhausted.
Diagnostic that settles it: the GPU showed **251 MB / 8,188 MB used the instant the
process died** — nothing external was holding memory, and the card was not too small.
(The earlier pilot never hit this because it spawned each run as a *subprocess*.)

**Fix:** one fresh process per run, so VRAM is fully reclaimed between runs.
`baseline` had already completed and its metrics were written, so it is **skipped, not
retrained** — no result was lost or silently recomputed.

Recorded because it is a reproducibility hazard for anyone rerunning this suite: training
several YOLO models in one process will OOM on a card this size, and the failure mode
(dying on run 2, not run 1) looks misleadingly like "the second condition needs more
memory".

### L13. RUN FAILURE — training killed by console-CLOSE, twice (Windows/MKL)
Two launch methods both died mid-training. Stderr gave the cause:

```
forrtl: error (200): program aborting due to window-CLOSE event
```

That is the **Intel Fortran runtime** (pulled in by NumPy/MKL). When the console that
owns the process closes, Windows sends `CTRL_CLOSE_EVENT` to every attached process, and
**MKL aborts instead of ignoring it**. The training was healthy at that instant (loss
falling, 2.7 it/s, epoch 1 in progress) — it was not crashing, it was being *executed by
the dying console*.

Died this way:
- `nohup python ... &` from the shell
- PowerShell `Start-Process` with redirected stdout/stderr

**Fix:** spawn with `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` (see
`rigor/launch_detached.py`). The child then owns **no console** and belongs to no console
process group, so `CTRL_CLOSE_EVENT` can never reach it.

Also changed the monitor to **detect the trainer's death**, not only its success. The
first failure was invisible for a long stretch precisely because a silent monitor and a
dead job look identical.

> Reproducibility hazard for anyone rerunning this suite on Windows: **long training runs
> must be detached from the console**, or any terminal/session close will abort them via
> MKL — with a Fortran error message that gives no hint that PyTorch or CUDA is involved.

### L14. PROVISIONAL — the causal fabrication ablation looks NULL
`A_contam_matched` (in flight): best mAP50 **0.892 @ ep25**, still 0.892 at ep50.
`baseline`: **0.890**.

**Essentially identical.** Swapping 459 tiles' labels from real pathologist boxes to
machine-written ones produced no measurable harm on the honest held-out slide.

Not final (run still going), but if it holds it is a **null result and will be reported
as one** — the brief requires inconclusive findings verbatim, not papered over.

**Why this is plausible, and why it matters:**

1. **Fabricated labels are not random noise.** They were produced by a *working vessel
   detector*, so they are mostly *correct* boxes on *real* vessels, plus some invented
   ones and some misses. A model trained on them still learns "a vessel looks like this."
   Box counts bear this out: fabricated 194 vs clean 200 on `A2FD_1_S.2058_26`; 77 vs 27
   on `S.2723_26_A2_FD_1` — comparable magnitude, not garbage.
2. **The matched dose is deliberately small** — 459 of 5,358 tiles (**~8.6%**), only 2 of
   10 slides. That is the price of a clean causal design: perfect control, modest dose.

**This does not weaken the paper — it sharpens it.** The danger of fabricated ground truth
was never mainly that it *degrades the detector*. It is that it **corrupts the
evaluation**: you score a model against another model's invented boxes and it looks
excellent. That is what `A_contam_fabval` measures, and that claim does **not** depend on
the collapse being large.

If the honest-slide harm is genuinely small while the *fabricated-validation* score is
inflated, the finding becomes sharper and more uncomfortable:

> Fabricated ground truth can leave the model roughly as good as before while making it
> **look far better than it is**. The damage is to measurement, not (necessarily) to
> learning — which is exactly why it went undetected for so long.

`A_contam_asitwas` (24% fabricated, realistic dose) will show whether harm appears at
higher contamination.

### L15. SILENT CORRUPTION — two trainers raced on the same run directory
**The most dangerous bug so far, and it was found by the user, not by any check of mine.**

`supervisor.py` was launched twice (once before a session teardown, once after). Both
survived. **Each spawned its own `run_ablations.py --run-all`.** Both selected the same
next-incomplete run (`A_contam_fabval`), both wrote to the **same output directory**, and
they overwrote one another — training was observed jumping from **epoch 81 back to epoch
1**.

**It was completely silent.** Nothing errored, nothing warned. It would have produced a
meaningless `results.csv` and a `metrics_final.json` derived from two interleaved
trainings, and that number would have gone into `results.json` looking exactly like a
real one.

In a paper *about* fabricated numbers, this is precisely the failure we cannot commit.

**Fixes:**
- exclusive **file lock** in `run_ablations.py --run-all`: a second instance detects the
  live holder and exits rather than racing (stale locks from dead holders are reclaimed)
- **supervisor removed** — it was the source of the double-launch. One detached trainer
  instead. Costs a manual restart after a teardown; far cheaper than silent corruption.

**Integrity verified after the fact:** the four completed runs (`baseline` 0.890 / ep79,
`A_contam_matched` 0.892 / ep76, `A_contam_asitwas` 0.891 / ep70, `B_sliding_window`
0.871 / ep96) were **untouched** — the race only affected the in-flight run, which was
deleted and restarted rather than trusted.

> **Reproducibility hazard:** any auto-restarting supervisor around Ultralytics needs a
> single-instance lock. Two runners writing one output directory corrupt results without
> raising a single error.

### L16. ⚠️ CONTRADICTS THE BRIEF — `A_contam_fabval` came out BACKWARDS
Brief §1a predicted: *"contaminated training scores **high** on its own fabricated
validation but collapses on the honest slide."*

**We measured the reverse.** Same model, two eval sets:

| evaluated on | mAP50 | mAP50-95 | P | R |
|---|---|---|---|---|
| honest `BFD_1` (real pathologist labels) | **0.882** | 0.599 | 0.906 | 0.765 |
| fabricated `S.3152_26_A3FD_1` (519 machine-labelled tiles, held out of training) | **0.124** | 0.033 | 0.236 | 0.245 |

`runs/A_contam_fabval/metrics_final.json`

**Why.** The model was trained **predominantly on clean data** — 8 clean slides vs 4
fabricated — so it learned what a *real* vessel looks like. Graded against invented boxes
it disagrees violently: **recall 0.245** means roughly **75% of the fabricated boxes
contain nothing a competent detector recognises as a vessel**.

**This is arguably a stronger result than the one predicted.** The fabricated "ground
truth" is not a *degraded* version of the truth — it is substantially **fictional**:

> A detector scoring **0.882** against real pathologist annotations scores **0.124**
> against the machine-fabricated ones. The two label sets describe almost different
> objects.

**Why the 0.705 leak was NOT reproduced.** To score *high* on fabricated labels a model
must be trained on the **same fabrication distribution** — it then learns to reproduce
that particular model's invented boxes (self-consistency). That is what the original
pipeline did. Our run is clean-dominated, so it cannot show that effect, and it did not.

**Consequence for the paper:** the "inflated score" claim is **NOT yet demonstrated** by
our runs. It requires a model trained *predominantly on fabricated labels*, evaluated on
held-out fabricated tiles. That run is proposed (`A_contam_heavy`) but **not yet
executed**. Until it is, we can state the *incompatibility* of the fabricated labels with
reality, but **not** that fabrication inflates scores.

Also note: `S.3152_26_A3FD_1` has **several different** fabricated `.ndpa` versions on
disk (301 / 131 / 146 / 298 boxes, from different inference runs). We used the 301-box
`A Files` copy. The original leaked run may have used a different one — so the fabricated
label distribution we evaluate against is not guaranteed to be the one the original model
was trained on. Another reason our number is not directly comparable to 0.705.

---

### L17. Ablation C complete — modest, consistent recall cost from blind negatives
`C_blind_negatives` (count-matched to `baseline`'s 2,097 negatives, same 5,303 total
training images, only negative *quality* differs):

| condition | mAP50 | mAP50-95 | P | R | ep |
|---|---|---|---|---|---|
| screened negatives (`baseline`) | 0.890 | 0.610 | 0.893 | 0.811 | 79 |
| blind negatives | 0.868 | 0.602 | 0.857 | 0.786 | 79 |
| **Δ (blind − screened)** | **−0.022** | −0.008 | −0.036 | **−0.025** |

Stability differs from the fabrication story: SD over training was *lower* for blind
negatives (0.032 vs baseline's 0.040) — this is a **consistent shift**, not the
instability collapse seen at 24% fabrication (L14). Recall drop is real but modest —
smaller than the ~30–48% contamination rate alone might suggest, because the count-match
means only a minority of training tiles carry the false "background" signal.

Heavy fabrication corpus (`A_contam_heavy`, run #8) finished building: 612 train tiles
(4 slides) + 216 held-out eval tiles (`S.3152_26_A3FD_1`), single `10xv25` fabrication
generation throughout per the two conditions agreed for that run.

`pilot_mosaic1` (run #7) is next — the epoch-cap decision.

---

### L18. Epoch-cap pilot complete — mosaic=1 converges ~2× later, as predicted
Both arms, one fold (`baseline`'s train/val split), seed 0, patience 60:

| arm | best mAP50 | best fitness (mAP50-95) | ran to | still improving at end |
|---|---|---|---|---|
| mosaic=0 | 0.890 @ ep17 | 0.610 @ **ep19** | 79 | No |
| mosaic=1 | 0.867 @ ep9 | 0.587 @ **ep37** | 97 | No |

Both genuinely converged and were caught by early stopping (patience counts from best
*fitness*, not mAP50 — L9). Neither was still improving at the point it stopped, so a cap
recommendation is valid per the brief's rule (§1b: refuse if either arm is still
improving).

**Mosaic=1's best fitness lands at ep37, ~2× later than mosaic=0's ep19** — confirms the
expected asymmetry the brief is built on: mosaic is a harder, more regularised task and
converges slower. Had the cap been read from mosaic=0 alone (ep19, or even its full ep79
stop), it would have cut mosaic=1 off before its true peak — this is the exact trap the
two-arm design exists to avoid.

**Cap, taken from the slower arm (mosaic=1) per the brief's rule:** best fitness ep37,
full natural stop at ep97 under patience=60. Recommended for the future full 264-run
grid: **keep the same patience=60 early-stopping rule** (already adaptive per-run) with a
ceiling around **120 epochs** — margin above this single fold's ep97 stop, since other
folds/seeds may converge slightly later. This is n=1 fold/seed; the brief's own §2 caveat
(close_mosaic=10 disables mosaic for the final 10 epochs) applies here too — the mosaic=1
run's late epochs were not *purely* mosaic.

Wall-clock: ~100s/epoch for this config → mosaic=1's 97 epochs ≈ 2.7h for one
(fold, arch, mosaic, seed) cell. Projected full grid at ceiling=120: 264 cells x ~120
epochs x ~100s ≈ 880 GPU-hours ≈ 37 GPU-days on this single RTX 4060 — far beyond the
20 July deadline on this hardware, consistent with brief §0.1's instruction NOT to run
the grid now.

---

### L19. `A_contam_heavy` was built but never wired into the runner
After 7 runs finished, `--run-all` exited immediately (exit code 0, no error) with all
7 skipped and nothing launched. Cause: `A_contam_heavy`'s tile corpus was built
(`build_heavy.py`, 1,224 train tiles across 4 fabricated slides + 216 held-out
fabricated eval tiles from `S.3152_26_A3FD_1`) but the run was never added to
`run_ablations.py`'s `ORDER` list or `build_conditions()` — so the orchestrator had
nothing left to do and quietly stopped.

Fixed: added the condition build (train = 4 fabricated slides' tiles, single `10xv25`
generation; eval = the same honest `BFD_1` set every other condition uses, PLUS a second
held-out-fabricated eval on `S.3152_26_A3FD_1`, mirroring the `A_contam_fabval` pattern),
added `"A_contam_heavy"` to `ORDER`, re-ran `--build` (verified: `train=1224 val=489 | 4
train slides | C1 ok`), confirmed training engaged (GPU 100%, 5553MiB) before moving on.

> Reproducibility note: a "did nothing, exited 0" outcome from an orchestrator can look
> identical to "finished successfully" if you only check the exit code. Always confirm
> against `status.py`'s run count, not just process exit status.

---

### L20. ALL 8 RUNS COMPLETE — `A_contam_heavy` confirms the inflation mechanism
`A_contam_heavy`: trained predominantly on fabricated labels (4 slides, single `10xv25`
generation, 1,224 train tiles), evaluated on the same honest `BFD_1` slide plus its own
held-out fabricated slide (`S.3152_26_A3FD_1`, 216 tiles, same generation, C1-held-out):

| | mAP50 | mAP50-95 | P | R |
|---|---|---|---|---|
| honest `BFD_1` | 0.194 | 0.036 | 0.268 | 0.345 |
| fabricated (held-out, same generation) | **0.457** | — | — | 0.454 |

**The direction flips exactly as predicted**, completing the two-sided story with
`A_contam_fabval`:

| run | training dominance | honest mAP50 | fabricated-eval mAP50 | Δ (fab − honest) |
|---|---|---|---|---|
| `A_contam_fabval` | clean-dominated | 0.882 | 0.124 | **−0.757** |
| `A_contam_heavy` | fabrication-dominated | 0.194 | 0.457 | **+0.263** |

When a model is trained predominantly on a fabrication generator's labels, it scores
**better against that generator's boxes than against real ones** — the self-consistency
signature the brief's §1a predicted. When clean-dominated, the reverse holds. Together
these two runs demonstrate the mechanism: **fabricated ground truth doesn't just fail to
teach real detection — training on it enough makes the model agree with the generator
more than with reality.**

**⚠️ Confound that must travel with this finding.** `A_contam_heavy`'s training set is
**1,224 tiles from 4 slides**, vs 5,303–5,511 tiles from 10–12 slides for every other
run (`manifest.json`, `n_train_images`). Its very low *absolute* honest-slide score
(0.194, vs 0.868–0.892 everywhere else) is confounded with having far less and less
diverse training data — NOT attributable to fabrication alone. **The within-model
comparison (fabricated eval vs honest eval, same trained weights) is NOT confounded by
this** — both evaluations use the identical checkpoint, so the +0.263 direction is solid
regardless of how weak the underlying model is. But do not cite 0.194 as "fabrication
destroys detection to this degree" — that number reflects data volume as much as data
quality.

**We still do not reproduce 0.705/0.780** (L16 already noted this): our fabricated-eval
score (0.457) uses the `10xv25` generation (131 boxes on the eval slide); the original
leaked run's generation is unknown. This stands as an independent controlled result, not
a replication.

**All 8 planned runs are now complete.** Ablation suite + epoch-cap pilot finished, per
brief §1a/§1b. No grid was run (§0.1 upheld throughout).

---

## Pending / open

- Ablation A/B/C metric deltas — runs in flight.
- Epoch cap — must come from the **mosaic=1** arm (it converges later; capping on the
  mosaic=0 arm would truncate it and *manufacture* the paper's hypothesis as a training
  artefact). Pilot refuses to recommend a cap if either arm is still improving.
- `close_mosaic=10` (Ultralytics default) disables mosaic for the final 10 epochs, so the
  mosaic arm is **not purely mosaic**. Biases *conservatively* (against the hypothesis)
  but must be stated whenever the grid is reported.
- Three slides remain permanently lost; their ground truth is unrecoverable.
- The 264-cell grid was **NOT run** and no grid results are reported (brief §0.1).

### AUTO — `A_contam_matched` completed (2026-07-14 01:39)

| metric | value |
|---|---|
| mAP50 | **0.892** (ep 25) |
| mAP50-95 | 0.615 (ep 16) |
| precision | 0.845 |
| recall | 0.789 |
| epochs run | 76 |
| s/epoch | 114 |

### AUTO — `A_contam_asitwas` completed (2026-07-14 04:03)

| metric | value |
|---|---|
| mAP50 | **0.891** (ep 10) |
| mAP50-95 | 0.613 (ep 10) |
| precision | 0.857 |
| recall | 0.835 |
| epochs run | 70 |
| s/epoch | 123 |

### AUTO — `B_sliding_window` completed (2026-07-14 06:47)

| metric | value |
|---|---|
| mAP50 | **0.871** (ep 36) |
| mAP50-95 | 0.599 (ep 36) |
| precision | 0.860 |
| recall | 0.779 |
| epochs run | 96 |
| s/epoch | 102 |
