# Release bundle — component manifest

One-line description of every component in the FAIR release bundle. Paths only, no
code bodies (per brief §3.5). Full tree: `release_tree.txt`.

| path | purpose |
|---|---|
| `RELEASE_README.md` | index + verification instructions for this bundle |
| `rigor/slides_clean.yaml` | **C2** — the frozen list of 11 ratified clean slides; the loader raises an error rather than falling back to globbing "all slides" if this file is missing or unreadable |
| `rigor/tiling_config.py` | single source of truth for tile size (1024px), per-scale downsample factor, and the size gates (`SNUG_FRAC=0.8`, `MIN_VISIBLE_FRAC=0.35`) that decide which annotations qualify at each scale |
| `rigor/tiling_fingerprint.py` | computes the corpus identity hash (config + slide list + tile content) used everywhere as `7b191fa9e02e`; **C3** — any run whose corpus does not hash to this value is refused |
| `rigor/backup.py` | writes and verifies `manifest.json`, a per-scale/per-split SHA-based hash of tile *labels* (not full images) plus image counts, so silent corpus drift is detectable |
| `rigor/contamination_audit.py` | fail-closed detector for machine-generated `.ndpa` files (vs genuine pathologist annotations); replaces an earlier fail-open guard that passed 2 of 8 known-contaminated files as clean |
| `rigor/regen_negatives.py` | builds the screened negative-tile set: a union of two independently-trained detectors plus test-time augmentation, because "no annotation overlap" alone is an unreliable definition of background (≈30-48% of such tiles contain a real, unlabelled vessel — see `verification.md` V3) |
| `rigor/tile_provenance.py` | per-tile (not per-slide) verification ledger — contamination is a property of individual annotations, so a slide can contain both trustworthy and untrustworthy tiles |
| `corpus_checksums.json` (generated; copy at `handoff/corpus_checksums.json`) | the actual checksum output of `backup.py`: `{"<scale>/<split>": {"n_images": ..., "label_hash": "..."}}` for every scale/split in the corpus; re-verified fresh against the live corpus at handoff time |

## Not included

Raw `.ndpi` whole-slide images and pathologist `.ndpa` annotation files are **not**
part of this bundle (size / potential data-use restrictions). The 264-cell experimental
grid was **not run** (brief §0.1) and has no artefacts to release.
