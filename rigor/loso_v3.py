"""
loso_v3.py — LOSO fold generator over the vessel-centred corpus (4.3, C1, C4).

The corpus is SLIDE-KEYED (tiles named `{slide}_{scale}_{x}_{y}`), so a fold is
just a partition of slide IDs — we never re-tile per fold. That is what makes the
zero-overlap property checkable rather than assumed.

For N clean slides we emit N folds, each holding out exactly ONE slide for eval.
The C1 assertion runs on the ACTUAL TILE FILENAMES of each fold, not on the
intended slide lists, so a mis-parsed name or a stray file cannot slip a slide
into both sides.

Also writes, per fold and per architecture, the ultralytics dataset.yaml:
    per_mag_3x     -> one yaml per scale (10x/20x/40x), three models
    single_allmag  -> one yaml pooling all three scales, one model
Both draw from the SAME tiles, so the architecture comparison is not confounded
by having different data.

    python loso_v3.py --write
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths
import tiling_config as TC
from slide_registry import AllowListError, load_clean_slides, load_raw

CORPUS = paths.TILES_V3
SPLIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "splits_v3")
MIN_EVAL_TILES = 5


def slide_of(fname, scale):
    m = f"_{scale}_"
    i = fname.rfind(m)
    return fname[:i] if i != -1 else None


def index_corpus(corpus=CORPUS):
    """-> {scale: {slide: {'pos': [...], 'neg': [...]}}} of label paths."""
    idx = {}
    for sc in TC.ALL_SCALES:
        per = {}
        for split, key in (("positives", "pos"), ("negatives", "neg")):
            d = os.path.join(corpus, f"training_data_{sc}", split, "labels")
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if not f.endswith(".txt") or f == "classes.txt":
                    continue
                sid = slide_of(f, sc)
                if sid is None:
                    continue
                per.setdefault(sid, {"pos": [], "neg": []})[key].append(
                    os.path.join(d, f))
        idx[sc] = per
    return idx


def assert_zero_overlap(fold, scale, train_paths, eval_paths):
    """C1 — enforced on real filenames. Raises on ANY shared slide."""
    tr = {slide_of(os.path.basename(p), scale) for p in train_paths} - {None}
    ev = {slide_of(os.path.basename(p), scale) for p in eval_paths} - {None}
    shared = tr & ev
    if shared:
        raise AssertionError(
            f"C1 VIOLATION fold {fold['fold']} @ {scale}: slide(s) in BOTH "
            f"train and eval: {sorted(shared)}")
    if ev and ev != {fold["held_out"]}:
        raise AssertionError(
            f"C1 VIOLATION fold {fold['fold']} @ {scale}: eval contains "
            f"slides other than the held-out one: {sorted(ev)}")


def build(slides, idx):
    folds = []
    for i, held in enumerate(sorted(slides)):
        train = sorted(s for s in slides if s != held)
        f = {"fold": i, "held_out": held, "train_slides": train, "scales": {}}
        for sc in TC.ALL_SCALES:
            ev = idx[sc].get(held, {}).get("pos", [])
            tr_p, tr_n = [], []
            for s in train:
                b = idx[sc].get(s, {"pos": [], "neg": []})
                tr_p += b["pos"]
                tr_n += b["neg"]
            assert_zero_overlap(f, sc, tr_p + tr_n, ev)
            f["scales"][sc] = {"n_eval_pos": len(ev),
                               "n_train_pos": len(tr_p),
                               "n_train_neg": len(tr_n)}
        folds.append(f)
    return folds


def _images_for(corpus, scales, slides):
    """Absolute image paths for the given slides at the given scales."""
    out = []
    for sc in scales:
        for split in ("positives", "negatives"):
            d = os.path.join(corpus, f"training_data_{sc}", split, "images")
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if not f.endswith(".png"):
                    continue
                if slide_of(os.path.splitext(f)[0], sc) in slides:
                    out.append(os.path.join(d, f))
    return out


def _write_listfile(path, images):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(images) + "\n")
    return path


def _assert_listfiles_disjoint(train_txt, val_txt, scales, fold):
    """C1, re-checked on the files ULTRALYTICS will actually read."""
    def slides_in(p):
        s = set()
        for ln in open(p, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            stem = os.path.splitext(os.path.basename(ln))[0]
            for sc in scales:
                sid = slide_of(stem, sc)
                if sid:
                    s.add(sid)
                    break
        return s

    tr, ev = slides_in(train_txt), slides_in(val_txt)
    shared = tr & ev
    if shared:
        raise AssertionError(
            f"C1 VIOLATION fold {fold['fold']}: slide(s) in BOTH train.txt and "
            f"val.txt: {sorted(shared)}  ({train_txt})")
    if ev and ev != {fold["held_out"]}:
        raise AssertionError(
            f"C1 VIOLATION fold {fold['fold']}: val.txt holds slides other than "
            f"the held-out one: {sorted(ev)}")


def write_yamls(folds, slides, out_dir, corpus=CORPUS):
    """Emit ultralytics dataset.yaml + explicit image-list files per fold.

    CRITICAL: ultralytics resolves `train:`/`val:` to DIRECTORIES and loads every
    image it finds; it silently ignores unknown keys. Listing the tile dirs and
    hoping a `_train_slides:` hint would filter them would have put every slide in
    BOTH train and val — a C1 violation, and precisely the "code path that could
    put tiles of the same slide in train and eval" the brief calls a bug.
    So we materialise explicit .txt image lists (ultralytics reads those) and then
    re-assert zero slide overlap on the files it will actually consume.
    """
    import yaml
    n = 0
    for f in folds:
        fdir = os.path.join(out_dir, f"fold{f['fold']}")
        os.makedirs(fdir, exist_ok=True)
        train_slides = set(f["train_slides"])
        held = {f["held_out"]}

        combos = [(f"per_mag_{sc}", [sc], "per_mag_3x", sc)
                  for sc in TC.CORE_SCALES]
        combos.append(("single_allmag", list(TC.CORE_SCALES), "single_allmag", "all"))

        for name, scales, arch, scale_tag in combos:
            tr_txt = _write_listfile(os.path.join(fdir, f"{name}_train.txt"),
                                     _images_for(corpus, scales, train_slides))
            ev_txt = _write_listfile(os.path.join(fdir, f"{name}_val.txt"),
                                     _images_for(corpus, scales, held))
            _assert_listfiles_disjoint(tr_txt, ev_txt, scales, f)

            doc = {
                "path": corpus,
                "train": tr_txt,
                "val": ev_txt,
                "nc": 1,
                "names": ["blood_vessel"],
                "_arch": arch,
                "_scale": scale_tag,
                "_fold": f["fold"],
                "_held_out_slide": f["held_out"],
                "_train_slides": sorted(train_slides),
            }
            with open(os.path.join(fdir, f"{name}.yaml"), "w") as fh:
                yaml.safe_dump(doc, fh, sort_keys=False)
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--corpus", default=CORPUS)
    args = ap.parse_args()

    if args.write:
        try:
            slides = load_clean_slides()          # C2 gate
        except AllowListError as exc:
            print(exc, file=sys.stderr)
            return 2
    else:
        slides = load_raw().get("include") or []
        print("*** PREVIEW — allow-list unratified; writing nothing ***\n")

    idx = index_corpus(args.corpus)
    present = [s for s in slides if any(s in idx[sc] for sc in TC.CORE_SCALES)]
    missing = [s for s in slides if s not in present]
    if missing:
        print(f"note: no tiles for {missing} (not tiled yet?)")

    folds = build(present, idx)

    hdr = f"{'fold':<5}{'held-out slide':<24}" + "".join(
        f"{sc + ' ev/tr':>14}" for sc in TC.CORE_SCALES)
    print(hdr)
    print("-" * len(hdr))
    for f in folds:
        row = f"{f['fold']:<5}{f['held_out']:<24}"
        for sc in TC.CORE_SCALES:
            s = f["scales"][sc]
            row += f"{str(s['n_eval_pos']) + '/' + str(s['n_train_pos']):>14}"
        print(row)
    print("-" * len(hdr))
    print(f"\nC1 zero-overlap assertion PASSED for {len(folds)} folds "
          f"x {len(TC.ALL_SCALES)} scales (checked on real tile filenames).")

    thin = [(f["fold"], f["held_out"], sc)
            for f in folds for sc in TC.CORE_SCALES
            if f["scales"][sc]["n_eval_pos"] < MIN_EVAL_TILES]
    if thin:
        print(f"\n!! folds with <{MIN_EVAL_TILES} eval tiles at a scale "
              f"(per-slide AP will be noisy):")
        for fo, sl, sc in thin:
            print(f"   fold {fo} ({sl}) @ {sc}")

    if not args.write:
        print("\nPreview only. Ratify slides_clean.yaml, then --write.")
        return 1

    os.makedirs(SPLIT_DIR, exist_ok=True)
    with open(os.path.join(SPLIT_DIR, "loso_folds.json"), "w") as fh:
        json.dump({"slides": present, "folds": folds,
                   "tiling": TC.as_dict()}, fh, indent=2)
    n = write_yamls(folds, present, SPLIT_DIR, args.corpus)
    print(f"\nwrote {SPLIT_DIR}/loso_folds.json + {n} dataset yamls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
