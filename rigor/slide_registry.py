"""
slide_registry.py — the single gate for constraint C2.

Every script that touches slide data must obtain its slide list from
`load_clean_slides()`. There is deliberately no fallback: if the allow-list is
absent, unratified, or malformed, this raises. It never globs the raw slide
directory and never degrades to "all slides".
"""

import os

import yaml

RIGOR_DIR = os.path.dirname(os.path.abspath(__file__))
ALLOWLIST = os.path.join(RIGOR_DIR, "slides_clean.yaml")

SCALES = ("10x", "20x", "40x")


class AllowListError(RuntimeError):
    """Raised whenever the clean slide allow-list cannot be trusted."""


def _fail(msg):
    raise AllowListError(
        f"{msg}\n\n"
        f"  allow-list: {ALLOWLIST}\n\n"
        "  Constraint C2 forbids falling back to the full slide set. Ratify the\n"
        "  allow-list (set `confirmed: true` and `confirmed_by`) before running\n"
        "  any split, training, evaluation, or aggregation step.\n"
        "  See BLOCKERS.md for why this gate exists."
    )


def load_clean_slides(path=ALLOWLIST, require_confirmed=True):
    """Return the ratified list of clean slide IDs. Raises if untrustworthy."""
    if not os.path.exists(path):
        _fail("STOP: the clean slide allow-list does not exist.")

    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    if not isinstance(doc, dict):
        _fail("STOP: allow-list is not a YAML mapping.")

    include = doc.get("include")
    if not include or not isinstance(include, list):
        _fail("STOP: allow-list has no non-empty `include:` list.")

    if require_confirmed:
        if doc.get("confirmed") is not True:
            _fail(
                "STOP: allow-list is present but NOT ratified "
                "(`confirmed:` is not true)."
            )
        if not doc.get("confirmed_by"):
            _fail("STOP: allow-list is marked confirmed but `confirmed_by:` is empty.")

    dupes = {s for s in include if include.count(s) > 1}
    if dupes:
        _fail(f"STOP: duplicate slides in allow-list: {sorted(dupes)}")

    excluded = set((doc.get("exclude") or {}).keys())
    overlap = excluded & set(include)
    if overlap:
        _fail(f"STOP: slides appear in BOTH include and exclude: {sorted(overlap)}")

    return list(include)


def load_raw(path=ALLOWLIST):
    """Read the allow-list without enforcing ratification (audit/report use only)."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


if __name__ == "__main__":
    doc = load_raw()
    print(f"allow-list      : {ALLOWLIST}")
    print(f"confirmed       : {doc.get('confirmed')}  by={doc.get('confirmed_by')}")
    print(f"include ({len(doc.get('include') or [])}) : {doc.get('include')}")
    print(f"exclude ({len(doc.get('exclude') or {})}) : {sorted((doc.get('exclude') or {}).keys())}")
    try:
        load_clean_slides()
    except AllowListError as exc:
        print(f"\ngate: BLOCKED (as expected while unratified)\n\n{exc}")
    else:
        print("\ngate: OPEN — downstream steps permitted.")
