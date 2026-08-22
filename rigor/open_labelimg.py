"""
open_labelimg.py — open a re-tiled scale/split in labelImg for review.

labelImg positional args are: IMAGE_DIR  PREDEFINED_CLASSES_FILE  SAVE_DIR.
We point it at a scale's images, its classes.txt, and its labels dir (so edits
save back as YOLO .txt in place).

NOTE: labelImg opens in its last-used format. On first run that is PascalVOC —
click the format button (left toolbar) once to switch to *YOLO* so the existing
boxes load and saves stay in YOLO .txt.

    python open_labelimg.py --dir <training_data_10x> --split positives
"""

import argparse
import os
import shutil
import subprocess
import sys

SPLITS = {
    "positives": ("train/positives/images", "train/positives/labels"),
    "negatives": ("train/negatives/images", "train/negatives/labels"),
    "val": ("val/images", "val/labels"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="a training_data_<scale> dir")
    ap.add_argument("--split", default="positives", choices=list(SPLITS))
    args = ap.parse_args()

    img_rel, lbl_rel = SPLITS[args.split]
    img_dir = os.path.join(args.dir, img_rel)
    lbl_dir = os.path.join(args.dir, lbl_rel)
    classes = os.path.join(lbl_dir, "classes.txt")

    for p in (img_dir, lbl_dir):
        if not os.path.isdir(p):
            sys.exit(f"missing: {p}")
    if not os.path.exists(classes):
        with open(classes, "w", encoding="utf-8") as fh:
            fh.write("blood_vessel\n")

    # Route through labelimg_launch.py, NOT labelImg.exe: stock labelImg 1.8.6
    # crashes on modern PyQt5 (float->int TypeErrors on paint/scroll/zoom).
    # The launcher patches those at runtime. See labelimg_launch.py.
    launcher = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "labelimg_launch.py")
    cmd = [sys.executable, launcher, img_dir, classes, lbl_dir]

    n = len([f for f in os.listdir(img_dir) if f.lower().endswith(".png")])
    print(f"opening labelImg: {n} images in {img_dir}")
    print("  -> if boxes don't show, click the format toggle to switch to YOLO")

    # Detach: a plain Popen child dies with this parent, so labelImg would
    # vanish the moment this script exits.
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NEW_PROCESS_GROUP)
    subprocess.Popen(cmd, close_fds=True, **kwargs)


if __name__ == "__main__":
    main()
