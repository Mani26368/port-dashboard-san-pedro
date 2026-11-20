"""Transforme le tableau "TEUs Archive Since 1995" du Port of Long Beach (copié depuis polb.com/statistics)
en data/clean/lb_teu_monthly.csv.

1. Sur polb.com (Port Statistics > "TEUs Archive: 1987 to present by month"), télécharge le CSV
   "Stats - TEU Archive Since 1995" et enregistre-le dans data/raw/polb_archive.csv.
   Colonnes lues : Date (ex. "Oct 2026"), Loaded Inbound, Loaded Outbound, Total Empties, Total.
2. Lance :  python scripts/clean_polb.py
Les mois déjà présents dans lb_teu_monthly.csv sont remplacés par ceux du fichier brut.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "polb_archive.csv"
OUT = ROOT / "data" / "clean" / "lb_teu_monthly.csv"


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def main():
    if not RAW.exists():
        raise SystemExit(f"Fichier introuvable : {RAW}")
    raw = pd.read_csv(RAW, dtype=str)
    df = pd.DataFrame({
        "month": pd.to_datetime(raw["Date"].str.strip(), format="%b %Y", errors="coerce"),
        "imports": num(raw["Loaded Inbound"]),
        "exports": num(raw["Loaded Outbound"]),
        "empties": num(raw["Total Empties"]),
        "total": num(raw["Total"]),
    }).dropna(subset=["month", "total"])
    df = df[df["month"] >= "2019-01-01"]
    old = pd.read_csv(OUT, parse_dates=["month"]) if OUT.exists() else pd.DataFrame(columns=df.columns)
    both = pd.concat([old[~old["month"].isin(df["month"])], df]).sort_values("month")
    both["month"] = both["month"].dt.strftime("%Y-%m-%d")
    both.to_csv(OUT, index=False)
    print(f"{len(both)} mois dans {OUT}")


if __name__ == "__main__":
    main()
