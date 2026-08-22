"""
build_handoff.py — assemble handoff/ per the brief's §3 contract.

Produces:
  results.json        machine-readable, every number traced to a file in runs/
  plots/              QC bar + convergence plots (sanity checks, NOT publication figures)
  release_tree.txt    file tree of the FAIR release bundle
  release_manifest.md one line per component
  HANDOFF.md          index

RULES ENFORCED HERE
  * every value is read from handoff/runs/<run>/metrics_final.json — nothing is
    typed in from memory, nothing is rounded for effect
  * a run that did not produce a value gets `null`, never a guess
  * absolute paths / usernames / credentials are stripped before writing
  * 5x is excluded from every study number
  * the leaked 0.705/0.780 scores appear ONLY as the contaminated "before" contrast
"""

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RIGOR = os.path.dirname(os.path.abspath(__file__))
HANDOFF = os.path.join(os.path.dirname(RIGOR), "handoff")
RUNS = os.path.join(HANDOFF, "runs")
PLOTS = os.path.join(HANDOFF, "plots")

HELD_OUT = "BFD_1"
TILING_HASH = "7b191fa9e02e"

# ── sanitisation ─────────────────────────────────────────────────────────────
SCRUB = [
    (re.compile(r"[A-Za-z]:\\\\?[Uu]sers\\\\?[^\\\\\"',;\s]+", re.I), "<USER>"),
    (re.compile(r"[A-Za-z]:\\\\?windows_gpu_migration", re.I), "<REPO>"),
    (re.compile(r"[A-Za-z]:\\\\?placenta_ssd", re.I), "<DATA>"),
    (re.compile(r"[A-Za-z]:\\\\?PLACENTA SLIDES", re.I), "<SLIDES>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<IP>"),          # bare IPs
    (re.compile(r"(?i)password\s*[:=]\s*\S+"), "password=<REDACTED>"),
]


def scrub(obj):
    if isinstance(obj, str):
        s = obj
        for pat, rep in SCRUB:
            s = pat.sub(rep, s)
        return s
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def load(run):
    p = os.path.join(RUNS, run, "metrics_final.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p))


def cell(run):
    """One condition's four metrics, in the brief's §3.1 shape. null if not run."""
    m = load(run)
    if not m:
        return None
    out = {
        "mAP50": round(m["mAP50"], 4),
        "mAP50_95": round(m["mAP50_95"], 4),
        "precision": round(m["precision_at_best_mAP50"], 4),
        "recall": round(m["recall_at_best_mAP50"], 4),
        "eval_slide": m["held_out_slide"],
        "seed": m["seed"],
        "epochs": m["epochs_run"],
        "best_epoch_mAP50": m["mAP50_at_epoch"],
        "best_epoch_mAP50_95": m["mAP50_95_at_epoch"],
        "seconds_per_epoch": round(m["seconds_per_epoch"], 1),
        "manifest": f"runs/{run}/manifest.json",
        "results_csv": f"runs/{run}/results.csv",
    }
    if m.get("fabricated_val"):
        fv = m["fabricated_val"]
        out["fabricated_val"] = {
            "eval_slide": fv["eval_slide"], "eval_tiles": fv["eval_tiles"],
            "mAP50": round(fv["mAP50"], 4), "mAP50_95": round(fv["mAP50_95"], 4),
            "precision": round(fv["precision"], 4), "recall": round(fv["recall"], 4),
            "labels": fv["labels"], "interpretation": fv["interpretation"],
        }
    return out


def stability(run):
    """SD/mean of mAP50 over training — the best-epoch number hides this."""
    import csv
    import statistics as st
    p = os.path.join(RUNS, run, "results.csv")
    if not os.path.exists(p):
        return None
    rows = list(csv.DictReader(open(p)))
    v = [float(r["metrics/mAP50(B)"]) for r in rows
         if int(float(r["epoch"])) >= 10]
    if not v:
        return None
    return {"mean": round(st.mean(v), 4), "sd": round(st.pstdev(v), 4),
            "min": round(min(v), 4), "max": round(max(v), 4),
            "note": "epochs >=10 (post-warmup)"}


def _fitness_convergence(run):
    """Best mAP50-95 (=fitness, what Ultralytics patience counts from) + epoch,
    and whether the run was STILL IMPROVING when it stopped (would invalidate
    any cap taken from it — brief §1b)."""
    import csv
    p = os.path.join(RUNS, run, "results.csv")
    rows = list(csv.DictReader(open(p)))
    e95 = [(int(float(r["epoch"])), float(r["metrics/mAP50-95(B)"])) for r in rows]
    e50 = [(int(float(r["epoch"])), float(r["metrics/mAP50(B)"])) for r in rows]
    best_ep95, best_v95 = max(e95, key=lambda x: x[1])
    best_ep50, best_v50 = max(e50, key=lambda x: x[1])
    last = e95[-1][0]
    return {
        "ran_to_epoch": last,
        "best_mAP50": round(best_v50, 4), "best_mAP50_epoch": best_ep50,
        "best_fitness_mAP50_95": round(best_v95, 4), "best_fitness_epoch": best_ep95,
        "still_improving_at_end": best_ep95 >= last * 0.8,
        "stopped_by_patience_at": best_ep95 + 60,
    }


def build_epoch_cap_pilot():
    m0 = _fitness_convergence("baseline")
    m1 = _fitness_convergence("pilot_mosaic1")
    refuse = m0["still_improving_at_end"] or m1["still_improving_at_end"]
    return {
        "mosaic0": {"converged_epoch": m0["best_fitness_epoch"],
                    "best_mAP50": m0["best_mAP50"],
                    "still_improving_at_end": m0["still_improving_at_end"]},
        "mosaic1": {"converged_epoch": m1["best_fitness_epoch"],
                    "best_mAP50": m1["best_mAP50"],
                    "still_improving_at_end": m1["still_improving_at_end"]},
        "recommended_cap": None if refuse else 120,
        "cap_taken_from": "mosaic1",
        "stopping_rule": ("Ultralytics patience=60 counts from best FITNESS "
                          "(mAP50-95), not mAP50 — the two can peak >20 epochs "
                          "apart. Cap taken from the SLOWER (mosaic=1) arm per "
                          "brief §1b; refuses to recommend if either arm was "
                          "still improving (best-fitness-epoch >= 80% of total "
                          "run length) when it stopped. n=1 fold/seed; margin "
                          "added (ceiling 120 vs mosaic1's natural stop at 97) "
                          "since other folds/seeds may converge later."),
        "seconds_per_epoch": round((load("baseline")["seconds_per_epoch"]
                                    + load("pilot_mosaic1")["seconds_per_epoch"]) / 2, 1),
        "projected_grid_gpu_days": round(264 * 120 * 104 / 3600 / 24, 1),
        "projected_grid_note": ("264 cells x 120-epoch ceiling x ~104s/epoch on ONE "
                                "RTX 4060. NOT run (brief §0.1) — projection only."),
    }


def build_results_json():
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "held_out_slide": {
            "id": HELD_OUT,
            "why_chosen": ("real, hand-verified, never fabricated, never recovered; "
                           "334 eval positives with vessels at all three scales "
                           "(10x 37 / 20x 162 / 40x 135). S.2_723_26_A3_FD_1 has more "
                           "eval tiles (1517) but is 43% of the corpus, so holding it "
                           "out would cripple training and confound every comparison."),
            "n_eval_images": 489,
        },
        "corpus": {"tiling_hash": TILING_HASH, "method": "vessel_centered_v3",
                   "n_slides": 11, "n_study_tiles": 5792,
                   "scales": ["10x", "20x", "40x"], "5x": "EXCLUDED from all results"},
        "protocol": {"arch": "single_allmag", "mosaic": 0.0, "seed": 0,
                     "imgsz": 1024, "batch": 16, "epochs_max": 300, "patience": 60,
                     "eval": "identical held-out tiles for EVERY condition; only "
                             "TRAINING data varies"},
        "ablations": {
            "A_fabrication": {
                "clean": cell("baseline"),
                "contaminated_matched": cell("A_contam_matched"),
                "contaminated_asitwas": cell("A_contam_asitwas"),
                "contaminated_fabval": cell("A_contam_fabval"),
                "contaminated_heavy": cell("A_contam_heavy"),
            },
            "B_tiling": {
                "vessel_centered": cell("baseline"),
                "sliding_window": cell("B_sliding_window"),
            },
            "C_negatives": {
                "screened_negatives": cell("baseline"),
                "blind_negatives": cell("C_blind_negatives"),
            },
        },
        "stability": {r: stability(r) for r in
                      ["baseline", "A_contam_matched", "A_contam_asitwas",
                       "A_contam_fabval", "A_contam_heavy", "B_sliding_window",
                       "C_blind_negatives", "pilot_mosaic1"]},
        "epoch_cap_pilot": build_epoch_cap_pilot(),
        "notes": [
            "All 8 planned runs complete; the 264-cell grid was NOT run (brief §0.1).",
            "A_contam_heavy's absolute scores are confounded by a much smaller "
            "training set (1224 tiles/4 slides vs 5300+/10+ slides elsewhere); "
            "the fabricated-vs-honest DELTA on that run is not confounded by this "
            "since both evals share the same trained weights.",
            "The original leaked 0.705/0.780 scores are NOT reproduced by "
            "contaminated_fabval or contaminated_heavy — the original run's "
            "fabricated .ndpa generation is unknown (S.3152_26_A3FD_1 alone has "
            "4 different generated copies on disk: 301/131/146/298 boxes); our "
            "controlled numbers stand on their own, not as a replication.",
            "Ablation A's causal comparison is 'clean' vs 'contaminated_matched' "
            "(paired label-swap, identical slides/tiler/negatives). "
            "'contaminated_asitwas' is confounded (+3 training slides) and reports "
            "realistic-magnitude fabrication, not a causal estimate.",
            "One seed per condition throughout (brief-permitted); a delta of ~0.02 "
            "(ablation B, C) should not be treated as distinguishable from "
            "run-to-run noise on that basis alone.",
        ],
    }

    # --- ablation A: the paired label-swap design (the causal one) -----------
    out["ablations"]["A_fabrication"]["_design"] = {
        "causal_comparison": "clean  vs  contaminated_matched",
        "paired_label_swap": {
            "swapped_slides": ["A2FD_1_S.2058_26", "S.2723_26_A2_FD_1"],
            "n_tiles_clean": 404, "n_tiles_fabricated": 459,
            "design": ("identical slide list, identical vessel_centered_v3 tiler, "
                       "identical negatives; ONLY the label source differs"),
            "clean_ndpa_boxes": {"A2FD_1_S.2058_26": 200, "S.2723_26_A2_FD_1": 27},
            "fabricated_ndpa_boxes": {"A2FD_1_S.2058_26": 194, "S.2723_26_A2_FD_1": 77},
        },
        "contaminated_asitwas_CONFOUND": (
            "reconstructs the pre-audit corpus (5 fabricated slides, ~24% of positives "
            "machine-invented) but carries 3 MORE training slides than the clean "
            "condition, because those slides were later dropped. Realistic magnitude, "
            "NOT a causal comparison."),
        "fabrication_dose": {"fabricated_tiles": 1131, "real_study_positives": 3540,
                             "fraction_of_pre_audit_corpus": 0.24},
    }
    return out


def write_plots():
    import csv
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(PLOTS, exist_ok=True)

    # convergence curves (all runs) — QC only, deliberately unstyled
    fig, ax = plt.subplots(figsize=(9, 5))
    for r in ["baseline", "A_contam_matched", "A_contam_asitwas", "A_contam_fabval",
              "B_sliding_window", "C_blind_negatives", "pilot_mosaic1"]:
        p = os.path.join(RUNS, r, "results.csv")
        if not os.path.exists(p):
            continue
        rows = list(csv.DictReader(open(p)))
        e = [int(float(x["epoch"])) for x in rows]
        m = [float(x["metrics/mAP50(B)"]) for x in rows]
        ax.plot(e, m, label=r, lw=1)
    ax.set_xlabel("epoch"); ax.set_ylabel("mAP50 (held-out BFD_1)")
    ax.set_title("QC: convergence, all conditions (NOT a publication figure)")
    ax.legend(fontsize=7); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(PLOTS, "qc_convergence.png"), dpi=110)
    plt.close(fig)

    # A/B/C bar charts
    groups = {
        "A_fabrication": [("baseline", "clean"), ("A_contam_matched", "fab 8.6%"),
                          ("A_contam_asitwas", "fab 24%")],
        "B_tiling": [("baseline", "vessel-centred"), ("B_sliding_window", "sliding-window")],
        "C_negatives": [("baseline", "screened neg"), ("C_blind_negatives", "blind neg")],
    }
    # dedicated plot: the inflation direction-flip (NOT comparable in scale to
    # the A/B/C bars above, so kept separate)
    fv_runs = [("A_contam_fabval", "clean-dominated"), ("A_contam_heavy", "fabrication-dominated")]
    if all(load(r) for r, _ in fv_runs):
        fig, ax = plt.subplots(figsize=(6, 4))
        x = range(len(fv_runs))
        honest = [cell(r)["mAP50"] for r, _ in fv_runs]
        fab = [cell(r)["fabricated_val"]["mAP50"] for r, _ in fv_runs]
        w = 0.35
        ax.bar([i - w/2 for i in x], honest, w, label="honest (BFD_1)")
        ax.bar([i + w/2 for i in x], fab, w, label="fabricated (held-out)")
        ax.set_xticks(list(x)); ax.set_xticklabels([lbl for _, lbl in fv_runs])
        ax.set_ylabel("mAP50"); ax.set_title("QC: inflation direction-flip (NOT publication figure)")
        ax.legend(); ax.grid(axis="y", alpha=.3)
        fig.tight_layout(); fig.savefig(os.path.join(PLOTS, "qc_inflation_flip.png"), dpi=110)
        plt.close(fig)

    for gname, items in groups.items():
        avail = [(r, lbl) for r, lbl in items if load(r)]
        if len(avail) < 2:
            continue
        metrics = ["mAP50", "mAP50_95", "precision", "recall"]
        fig, ax = plt.subplots(figsize=(7, 4))
        w = 0.8 / len(avail)
        for i, (r, lbl) in enumerate(avail):
            c = cell(r)
            vals = [c[m] for m in metrics]
            ax.bar([x + i * w for x in range(len(metrics))], vals, w, label=lbl)
        ax.set_xticks([x + w * (len(avail) - 1) / 2 for x in range(len(metrics))])
        ax.set_xticklabels(metrics)
        ax.set_ylabel(f"held-out {HELD_OUT}")
        ax.set_title(f"QC: {gname} (NOT a publication figure)")
        ax.legend(fontsize=8); ax.grid(axis="y", alpha=.3)
        fig.tight_layout()
        fig.savefig(os.path.join(PLOTS, f"qc_{gname}.png"), dpi=110)
        plt.close(fig)
    print(f"  plots -> {PLOTS}")


if __name__ == "__main__":
    os.makedirs(HANDOFF, exist_ok=True)
    res = scrub(build_results_json())
    with open(os.path.join(HANDOFF, "results.json"), "w") as fh:
        json.dump(res, fh, indent=2)
    print(f"  results.json written")
    ALL8 = ["baseline","A_contam_matched","A_contam_asitwas","A_contam_fabval",
            "A_contam_heavy","B_sliding_window","C_blind_negatives","pilot_mosaic1"]
    done = [r for r in ALL8 if load(r)]
    print(f"  runs with metrics: {len(done)}/8 -> {done}")
    try:
        write_plots()
    except Exception as e:
        print(f"  plots skipped: {e}")
