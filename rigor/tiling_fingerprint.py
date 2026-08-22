"""
tiling_fingerprint.py — constraint C3.

Stamps every run with a hash of (tiling parameters + clean slide list + the
actual tile corpus). Runs whose fingerprints differ were trained on different
data and MUST NOT be aggregated or plotted together.

Three components:

  param_hash   — the tiling knobs, read from prepare_training_tiles.py rather
                 than retyped here, so the fingerprint cannot silently drift
                 out of sync with the code that produced the tiles.
  slides_hash  — the ratified clean slide list.
  corpus_hash  — the bytes of every label file plus the name+size of every
                 image, per scale. This is what actually catches a regenerated
                 or hand-edited tile set, which a param hash alone would miss.

`fingerprint()` returns the short composite used as `tiling_hash` in run
metadata. `refuse_mixed()` is the aggregation guard.
"""

import ast
import hashlib
import json
import os

import paths
from slide_registry import SCALES, load_clean_slides

RIGOR_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(RIGOR_DIR)
TILER_SRC = os.path.join(PROJECT_DIR, "prepare_training_tiles.py")
DATA_ROOT = paths.TILES_V3   # vessel-centred corpus (v3)

# Module-level tiling knobs to lift out of prepare_training_tiles.py.
PARAM_NAMES = [
    "TILE_SIZE",
    "OVERLAP",
    "MIN_ANN_OVERLAP",
    "MAX_NEG_RATIO",
    "WHITE_THRESH",
    "VAL_FRAC",
]
# Per-scale gates live in the SCALE_CFG-style dict; we capture these keys.
SCALE_KEYS = ("downsample", "min_l0_px", "max_l0_px")


def _short(h):
    return h.hexdigest()[:12]


def read_tiling_params(src=None):
    """The live tiling parameters (constraint C3).

    Reads rigor/tiling_config.py — the single source of truth for the
    vessel-centred tiler. It used to static-parse prepare_training_tiles.py, but
    that is the OLD whole-slide sliding-window tiler we abandoned (it put the
    vessel on a tile edge in 58% of tiles). Hashing it would have stamped every
    run with a fingerprint describing tiling we no longer use — silently
    defeating the very guard C3 exists to provide.
    """
    import tiling_config
    import importlib
    importlib.reload(tiling_config)
    return tiling_config.as_dict()


def param_hash(params=None):
    params = params or read_tiling_params()
    blob = json.dumps(params, sort_keys=True).encode()
    return _short(hashlib.sha256(blob))


def slides_hash(slides=None):
    slides = slides or load_clean_slides()
    blob = json.dumps(sorted(slides)).encode()
    return _short(hashlib.sha256(blob))


def corpus_hash(slides=None, data_root=DATA_ROOT, scales=SCALES):
    """Hash label bytes + image (name, size) for tiles of the clean slides only."""
    slides = slides or load_clean_slides()
    h = hashlib.sha256()

    for scale in scales:
        root = os.path.join(data_root, f"training_data_{scale}")
        entries = []
        for dirpath, _, files in os.walk(root):
            for f in sorted(files):
                if f.startswith("._") or f == "classes.txt":
                    continue
                slide = slide_of(f, scale)
                if slide not in slides:
                    continue
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if f.endswith(".txt"):
                    with open(full, "rb") as fh:
                        entries.append((rel, hashlib.sha256(fh.read()).hexdigest()))
                elif f.lower().endswith((".png", ".jpg", ".jpeg")):
                    entries.append((rel, str(os.path.getsize(full))))
        for rel, digest in sorted(entries):
            h.update(f"{scale}/{rel}:{digest}\n".encode())

    return _short(h)


def slide_of(fname, scale):
    """'{slide}_{scale}_{x}_{y}[.dupN].ext' -> slide id, or None."""
    marker = f"_{scale}_"
    idx = fname.rfind(marker)
    return fname[:idx] if idx != -1 else None


def fingerprint(slides=None):
    slides = slides or load_clean_slides()
    params = read_tiling_params()
    parts = {
        "param_hash": param_hash(params),
        "slides_hash": slides_hash(slides),
        "corpus_hash": corpus_hash(slides),
    }
    composite = hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode()
    )
    parts["tiling_hash"] = _short(composite)
    parts["params"] = params
    parts["n_slides"] = len(slides)
    return parts


def refuse_mixed(run_metas):
    """Guard for constraint C3. `run_metas` is an iterable of per-run dicts."""
    seen = {}
    for meta in run_metas:
        th = meta.get("tiling_hash")
        if not th:
            raise RuntimeError(
                f"run {meta.get('run_id')!r} has no tiling_hash — refusing to aggregate."
            )
        seen.setdefault(th, []).append(meta.get("run_id"))

    if len(seen) > 1:
        lines = "\n".join(f"  {h}: {sorted(r)}" for h, r in sorted(seen.items()))
        raise RuntimeError(
            "REFUSING to aggregate runs across differing tiling hashes (C3).\n"
            "These runs were trained on different data:\n" + lines
        )
    return next(iter(seen)) if seen else None


if __name__ == "__main__":
    params = read_tiling_params()
    print("tiling parameters recovered from prepare_training_tiles.py:")
    print(json.dumps(params, indent=2, sort_keys=True))
    print(f"\nparam_hash = {param_hash(params)}")
    try:
        fp = fingerprint()
    except Exception as exc:  # AllowListError while unratified
        print(f"\ncorpus/slides hash unavailable:\n{exc}")
    else:
        print(f"slides_hash = {fp['slides_hash']}")
        print(f"corpus_hash = {fp['corpus_hash']}")
        print(f"TILING_HASH = {fp['tiling_hash']}")
