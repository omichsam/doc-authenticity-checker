"""
Score genuine held-out pages so the API can say how a page compares with real ones.

Rebuilds the notebook's leakage-safe split (same seed and grouping), scores every genuine
validation and test page with the current checkpoint, and writes genuine_scores.json.
Re-run after retraining (needs the notebook's data/ folder):
    python calibrate.py
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from tamper_core import Checker, load_image

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
MODEL_PATH = HERE / "tamper_cnn.pt"
OUT = HERE / "genuine_scores.json"
SEED = 42
EXPECTED = {"train": 461, "val": 67, "test": 55}   # page counts printed by the notebook


def notebook_split() -> pd.DataFrame:
    rows = []
    for p in sorted((DATA / "clinocr").rglob("*.jpg")):
        if "scans" in p.parts:
            rows.append(dict(path=p, group="clin_t" + re.search(r"template_(\d+)", p.stem).group(1)))
    for p in sorted((DATA / "funsd").rglob("*.png")):
        if p.parent.name == "images" and "__MACOSX" not in p.parts:
            rows.append(dict(path=p, group="funsd_" + p.stem))
    df = pd.DataFrame(rows)
    groups = df["group"].drop_duplicates().sample(frac=1, random_state=SEED).tolist()
    n = len(groups)
    df["split"] = df["group"].map({g: "test" if i < 0.15 * n else "val" if i < 0.30 * n else "train"
                                   for i, g in enumerate(groups)})
    return df


def main() -> None:
    df = notebook_split()
    counts = df["split"].value_counts().to_dict()
    if counts != EXPECTED:
        raise SystemExit(f"Split does not match the notebook ({counts} vs {EXPECTED}); is data/ complete?")

    checker = Checker.load(MODEL_PATH)
    held_out = df[df["split"].isin(["val", "test"])]
    scores = []
    for i, p in enumerate(held_out["path"], 1):
        scores.append(checker.predict(load_image(p))[2])
        print(f"\r{i}/{len(held_out)}", end="", flush=True)
    print()

    OUT.write_text(json.dumps({
        "model_sha256": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "genuine validation + test pages (ClinOCR-Bench, FUNSD), never used for training",
        "n": len(scores),
        "scores": sorted(round(s, 5) for s in scores),
    }, indent=1))
    print(f"Saved {len(scores)} genuine scores to {OUT.name}")


if __name__ == "__main__":
    main()
