# -*- coding: utf-8 -*-
"""Quick scan train_ori CSV files for label coverage."""
from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parents[1] / "datasets/相关数据/train_ori"
for p in sorted(root.glob("*.csv")):
    try:
        df = pd.read_csv(p)
    except Exception as exc:
        print(p.name, "ERROR", exc)
        continue
    label_col = None
    for c in df.columns:
        if c == "label" or c.startswith("label"):
            label_col = c
            break
    rows = len(df)
    labeled = int(df[label_col].notna().sum()) if label_col else 0
    print(f"{p.name}\trows={rows}\tlabel_col={label_col}\tlabeled={labeled}")
