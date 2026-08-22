"""
labelimg_launch.py — run labelImg 1.8.6 on modern PyQt5 without the float/int crashes.

THE PROBLEM
labelImg 1.8.6 predates PyQt5's strict argument typing. Qt's C++ APIs take ints,
but labelImg computes coordinates in float (QPointF.x(), scale multiplications,
`singleStep() * units`). Old PyQt5 silently coerced float->int; current PyQt5
raises TypeError. labelImg is deprecated upstream, so this is never getting fixed
there.

It is NOT one bug — it is every place a computed float reaches a Qt int API:

    libs/canvas.py:526    p.drawRect(left_top.x(), ...)        -> paint
    libs/canvas.py:530-1  p.drawLine(self.prev_point.x(), ...) -> crosshair, fires
                                                                  as soon as the
                                                                  mouse enters the
                                                                  canvas
    labelImg.py:965       bar.setValue(... singleStep() * units) -> mouse wheel
    labelImg.py:1025-6    h_bar/v_bar.setValue(...)              -> pan/scroll
    labelImg.py:971       zoom_widget.setValue(value)            -> zoom

Patching them one at a time is whack-a-mole; the user hits the next one on the
next mouse gesture.

THE FIX
Wrap the offending Qt methods once, at the class level, to coerce float->int —
restoring the old PyQt5 behaviour these call sites were written against. We do
this at RUNTIME, from this repo. site-packages is left untouched, so a pip
upgrade cannot silently revert it and nothing on the machine is mutated behind
the user's back.

    python labelimg_launch.py <image_dir> <classes.txt> <save_dir>
    python labelimg_launch.py --self-test      # exercise every crash path
"""

import os
import sys

from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QAbstractSlider, QSpinBox

# (class, method) pairs that take ints but get handed floats by labelImg.
TARGETS = [
    (QPainter, "drawLine"),
    (QPainter, "drawRect"),
    (QPainter, "drawEllipse"),
    (QAbstractSlider, "setValue"),   # QScrollBar: wheel-scroll + pan
    (QSpinBox, "setValue"),          # ZoomWidget: zoom
]


def _coerce(args):
    return tuple(int(a) if isinstance(a, float) else a for a in args)


def _wrap(cls, name):
    orig = getattr(cls, name)

    def wrapper(self, *args, **kwargs):
        try:
            return orig(self, *args, **kwargs)
        except TypeError:
            # only retry when float->int coercion could plausibly help
            return orig(self, *_coerce(args), **kwargs)

    setattr(cls, name, wrapper)


def patch():
    for cls, name in TARGETS:
        _wrap(cls, name)


def self_test():
    """Exercise each real crash path with the float values labelImg produces."""
    from PyQt5.QtWidgets import QApplication, QScrollBar
    from PyQt5.QtGui import QPixmap

    app = QApplication(sys.argv[:1])
    results = []

    # crash path 1+2: canvas.py paintEvent (drawLine / drawRect with QPointF.x())
    pm = QPixmap(100, 100)
    p = QPainter()
    p.begin(pm)
    try:
        p.drawLine(12.5, 0, 12.5, 100.0)      # canvas.py:530
        p.drawRect(1.5, 2.5, 10.5, 20.5)      # canvas.py:526
        results.append(("QPainter.drawLine/drawRect (paint, crosshair)", "OK"))
    except TypeError as e:
        results.append(("QPainter.drawLine/drawRect", f"FAIL {e}"))
    p.end()

    # crash path 3: labelImg.py:965 scroll_request (mouse wheel)
    bar = QScrollBar()
    bar.setMaximum(500)
    try:
        bar.setValue(bar.value() + bar.singleStep() * 1.5)   # float
        results.append(("QScrollBar.setValue (mouse wheel / pan)", "OK"))
    except TypeError as e:
        results.append(("QScrollBar.setValue", f"FAIL {e}"))

    # crash path 4: labelImg.py:971 zoom
    sb = QSpinBox()
    sb.setMaximum(500)
    try:
        sb.setValue(137.4)
        results.append(("QSpinBox.setValue (zoom widget)", "OK"))
    except TypeError as e:
        results.append(("QSpinBox.setValue", f"FAIL {e}"))

    ok = all(r[1] == "OK" for r in results)
    for what, res in results:
        print(f"  [{res:<4}] {what}" if res == "OK" else f"  [FAIL] {what}: {res}")
    print("\nself-test:", "ALL CRASH PATHS PATCHED" if ok else "*** STILL BROKEN ***")
    return 0 if ok else 1


def sanitize_classes(path):
    """Strip a UTF-8 BOM from classes.txt.

    labelImg reads classes.txt, keeps whatever it finds as the class NAME, then
    writes it back with the system codec (cp1252 on Windows). A BOM ('\\ufeff')
    therefore explodes on the FIRST SAVE — i.e. the moment you draw a box:

        libs/yolo_io.py:77  out_class_file.write(c + '\\n')
        UnicodeEncodeError: 'charmap' codec can't encode character '\\ufeff'

    PowerShell 5.1's `Set-Content -Encoding utf8` emits a BOM, which is exactly
    how ours got one. Rewrite it as plain ASCII before launching.
    """
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return
    txt = raw.decode("utf-8-sig", errors="replace")           # -sig drops the BOM
    lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    clean = "\n".join(lines) + "\n"
    if clean.encode("ascii", errors="replace") != raw:
        with open(path, "w", encoding="ascii", errors="replace", newline="\n") as fh:
            fh.write(clean)
        print(f"  sanitised {os.path.basename(path)} (removed BOM / stray bytes)")


def main():
    patch()
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    # argv: [launcher, image_dir, classes.txt, save_dir]
    if len(sys.argv) > 2:
        sanitize_classes(sys.argv[2])
    from labelImg import labelImg as app   # import AFTER patching
    app.main()


if __name__ == "__main__":
    main()
