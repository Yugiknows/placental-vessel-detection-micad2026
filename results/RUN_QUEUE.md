# Run Queue — status of every training session

Single source of truth for what has run, what is running, and what is next.
Updated as runs land. Every number here traces to `runs/<name>/metrics_final.json`.

**Protocol (identical for every run):** `single_allmag`, mosaic=0 (except the pilot's
mosaic arm), seed 0, imgsz 1024, batch 16, epochs≤300, patience 60.
**Corpus:** `vessel_centered_v3`, hash `7b191fa9e02e`, 11 slides, 5,792 study tiles
(10×/20×/40×; **5× excluded**).
**Held-out slide (all runs):** `BFD_1` — 489 eval images. Only the TRAINING data varies.

Clearing policy: a run is *complete* only when `metrics_final.json` exists — those are
skipped forever. A killed *partial* (results.csv, no metrics) is **deleted and re-run**,
never resumed, because resuming into a stale directory can interleave two trainings into
one results.csv.

---

## ✅ ALL 8 RUNS COMPLETE

| # | run | mAP50 | mAP50-95 | P | R | ep | what it answers |
|---|---|---|---|---|---|---|---|
| 1 | `baseline` | **0.890** | 0.610 | 0.893 | 0.811 | 79 | clean reference (= A_clean, B_vessel, C_screened, pilot mosaic0) |
| 2 | `A_contam_matched` | 0.892 | 0.615 | 0.845 | 0.789 | 76 | **causal** fabrication (8.6%): identical slides/tiler/negatives, only 459 tiles' labels swapped |
| 3 | `A_contam_asitwas` | 0.891 | 0.613 | 0.857 | 0.835 | 70 | pre-audit corpus (24% fabricated) — *confounded: 3 extra slides* |
| 4 | `A_contam_fabval` | 0.882 | 0.599 | 0.906 | 0.765 | 80 | + FABRICATED-VAL: mAP50 **0.124**, R 0.245 (clean-dominated model) |
| 5 | `B_sliding_window` | 0.871 | 0.599 | 0.860 | 0.779 | 96 | old sliding-window tiling |
| 6 | `C_blind_negatives` | 0.868 | 0.602 | 0.857 | 0.786 | 79 | recall cost of unscreened negatives. **Count-matched** (2,097 negatives, same as screened) so only *quality* varies |
| 7 | `pilot_mosaic1` | 0.867 | 0.587 | 0.839 | 0.792 | 97 | epoch cap — the **slow arm**. Best fitness ep37 vs mosaic0's ep19 (~2×) |
| 8 | `A_contam_heavy` | 0.194 | 0.036 | 0.268 | 0.345 | 71 | + FABRICATED-VAL: mAP50 **0.457**, R 0.454 (fabrication-dominated, only 1,224 train tiles/4 slides — confounded, see finding below) |

---

## Findings so far

**Ablation A — fabrication**
- **8.6% (causal): NO harm.** 0.892 vs 0.890. Fabricated boxes came from a *working*
  detector (194 vs 200 real boxes on one slide, 77 vs 27 on the other) — a degraded
  version of truth, not noise.
- **24%: same peak, but training destabilises.** SD **0.171 vs 0.040** (4.3×), mean 0.682
  vs 0.840, worst epoch 0.170. **Best-epoch reporting hides this completely** — the
  headline metric says 0.891, i.e. "no harm".
- **Fabricated labels are substantially fictional.** A model scoring **0.882** on real
  annotations scores **0.124** against machine-invented ones (recall 0.245 → ~75% of
  fabricated boxes contain nothing a competent detector sees).
- **Inflation confirmed via direction-flip (run #8).** Clean-dominated model
  (`A_contam_fabval`): honest 0.882 vs fabricated 0.124 (Δ **−0.757**). Fabrication-
  dominated model (`A_contam_heavy`): honest 0.194 vs fabricated **0.457** (Δ **+0.263**).
  The sign flips exactly as the brief's §1a predicted: a model trained on a fabrication
  generator's labels scores *better* against that generator's boxes than against reality.
  ⚠️ `A_contam_heavy`'s absolute numbers are confounded by a much smaller training set
  (1,224 tiles/4 slides vs 5,300+/10+ slides elsewhere) — the **within-model** fab-vs-honest
  delta is not confounded by this (same weights, two eval sets), but do not cite 0.194 as a
  clean measure of "how much fabrication alone costs". We still do not reproduce 0.705/0.780
  (unknown original fabrication generation; ours is `10xv25`).

**Ablation B — tiling**
- Sliding-window costs **−0.020 mAP50, −0.033 recall**. Real but **modest** — far less
  than the 58%→16% edge-clip geometry might suggest. Consistent across the whole run
  (training mean 0.784 vs 0.840), not just at the peak.
- Caveat: trained on sliding-window tiles, *evaluated* on vessel-centred ones (the eval
  set must be constant), so part of the penalty is a train/test framing mismatch.

**Ablation C — negatives**
- Blind (unscreened) negatives cost **−0.022 mAP50, −0.025 recall, −0.036 precision**
  vs screened negatives, holding positives and image count constant (5,303 both sides).
  Modest and consistent — similar magnitude to the tiling ablation, not the dramatic
  effect the ~30–48% contamination rate might suggest.
- Note: SD over training was actually *lower* for blind negatives (0.032 vs 0.040) —
  unlike the fabrication ablation, this is a consistent shift, not a stability collapse.
- Interpretation: the count-matched screened set means recall roughly tracks how often
  the model is (wrongly) told a real vessel is background — modest here because the
  contamination rate, while real, is a minority of tiles.

**Epoch cap (run #7, `pilot_mosaic1`)**
- Best fitness (mAP50-95): mosaic=0 at **ep19**, mosaic=1 at **ep37** — mosaic converges
  ~2× later, as predicted. Neither arm was still improving when it stopped (both caught by
  patience=60 naturally) — a cap recommendation is valid per the brief's rule.
- **Recommended for a future grid:** keep patience=60 (adaptive per-run), ceiling ≈120
  epochs (margin above this single fold's ep97 natural stop). n=1 fold/seed — would need
  validation across more folds before finalising for the full 264-run grid.
- Wall-clock: ~100–108 s/epoch this hardware. Full grid at ceiling=120 ≈ 880 GPU-hours ≈
  37 GPU-days on one RTX 4060 — confirms brief §0.1's instruction not to run the grid now.

---

## Limitations that must reach the paper

1. **One seed per cell.** A Δ of ~0.02 (ablation B) cannot be confidently separated from
   seed noise. Direction + whole-curve consistency is the evidence, not the point estimate.
2. **Absolute values are `BFD_1`-specific.** The same config scored 0.890 on `BFD_1` and
   0.731 on `A2FD_1` — the *slide* moved the number by 0.16. Deltas are valid; absolutes
   are not generalisable.
3. **`A_contam_asitwas` is confounded** (3 extra slides). Causal claims rest on
   `A_contam_matched`.
4. **The screened negatives' "0% contaminated" is circular** — those tiles were selected
   by rejecting what that same model flagged. The independent check is the human labelImg
   review.
5. **We do not reproduce 0.705.** The original run's fabricated `.ndpa` copy is unknown
   (`S.3152_26_A3FD_1` has four: 301/131/146/298 boxes). `A_contam_heavy` stands on its
   own as a controlled result, not a replication.
6. **`close_mosaic=10`** (Ultralytics default) disables mosaic for the last 10 epochs, so
   the mosaic arm is not *purely* mosaic. Biases conservatively; must be stated.
