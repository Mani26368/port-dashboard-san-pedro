"""Tableau de bord portuaire : San Pedro Bay (Los Angeles + Long Beach) face aux autres ports.
Lancer :  streamlit run app.py
L'appli ne lit que des fichiers dans data/clean/ : elle n'appelle aucune API et ne contient aucune clé.
"""
import json
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data" / "clean"))

# Seuils choisis par l'auteur : à ajuster et à justifier dans la fiche de conception
GUST_ALERT_KMH = 50      # rafales au-dessus : risque pour les grues
WAVE_ALERT_M = 2.5       # vagues au-dessus : risque pour les pilotes et les remorqueurs
AIS_CROWD_ALERT = 40     # navires dans la zone au-dessus : congestion possible
VOLUME_ALERT = 0.90      # alerte si le mois est sous 90 % de la moyenne des 12 mois précédents
FORECAST_MONTHS = 6

st.set_page_config(page_title="Tableau de bord San Pedro Bay", page_icon="⚓", layout="wide")

# Couleurs (palette validée : violet = Los Angeles, rose = Long Beach, rouge = alerte)
NAVY, BLUE, ORANGE, RED, GREY = "#2b1055", "#6250d6", "#d55181", "#e34948", "#b9b3c9"

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1400px;}
header[data-testid="stHeader"] {background: transparent;}
.hero {background: linear-gradient(120deg, #2b1055 0%, #6250d6 55%, #d55181 100%); color: #fff;
       border-radius: 18px; padding: 26px 32px; margin-bottom: 18px;
       box-shadow: 0 6px 20px rgba(43,16,85,.22);}
.hero .eyebrow {letter-spacing: .14em; font-size: .75rem; opacity: .8; font-weight: 600;}
.hero h1 {color: #fff; font-size: 2.1rem; margin: 4px 0 6px 0; padding: 0; line-height: 1.15;}
.hero p {margin: 0 0 14px 0; opacity: .92; font-size: 1rem; max-width: 900px;}
.hero .chip {display: inline-block; background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.28);
             border-radius: 999px; padding: 4px 14px; margin: 0 8px 6px 0; font-size: .82rem;}
.sec {display: flex; align-items: center; gap: 12px; margin: 22px 0 8px 0;}
.sec .num {background: #6250d6; color: #fff; border-radius: 10px; width: 34px; height: 34px;
           display: flex; align-items: center; justify-content: center; font-weight: 700;}
.sec h3 {margin: 0; padding: 0; font-size: 1.35rem; color: #2b1055;}
.sec p {margin: 0; font-size: .85rem; color: #6b5f85;}
[class*="st-key-tile_"] {background: #fff; border: 1px solid #e3daf0 !important; border-left: 6px solid #6250d6 !important;
        border-radius: 14px !important; box-shadow: 0 2px 8px rgba(43,16,85,.07); min-height: 330px;}
[class*="st-key-tile_alert"] {border-left-color: #e34948 !important; background: #fff3f5;}
[class*="st-key-tile_"] [data-testid="stMetricValue"] {font-size: 2.1rem; font-weight: 700; color: #2b1055;}
[class*="st-key-tile_"] [data-testid="stMetricLabel"] {color: #6b5f85; font-weight: 600;}
.tag {display: inline-block; font-size: .68rem; letter-spacing: .1em; font-weight: 700; color: #4a3aa7;
      background: #efeafc; border-radius: 6px; padding: 2px 8px; margin-bottom: 4px;}
.pill {display: inline-block; font-size: .72rem; font-weight: 700; border-radius: 999px; padding: 2px 10px; margin-right: 6px;}
.pill.ok {background: #e3f6ee; color: #0a6b4a;}
.pill.alert {background: #fde4e4; color: #b3261e;}
div[data-testid="stAlert"] {border-radius: 12px;}
[data-testid="stDataFrame"] {border-radius: 12px; overflow: hidden; border: 1px solid #e3daf0;}
.foot {margin-top: 28px; padding: 14px 18px; border-top: 1px solid #e3daf0; color: #6b5f85; font-size: .82rem;}
</style>
""", unsafe_allow_html=True)


def section(num, title, sub=""):
    st.markdown(f'<div class="sec"><div class="num">{num}</div><div><h3>{title}</h3><p>{sub}</p></div></div>',
                unsafe_allow_html=True)


def style_fig(fig, height):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color=NAVY),
                      legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(showgrid=False, linecolor="#d6cce8")
    fig.update_yaxes(gridcolor="#ece6f5", zeroline=False)
    return fig


# ---------- Lecture des fichiers (avec message clair si absents) ----------
@st.cache_data(ttl=3600)
def load_csv(name, mtime):
    path = DATA / name
    return pd.read_csv(path)


def read_csv(name):
    path = DATA / name
    if not path.exists():
        return None
    try:
        df = load_csv(name, path.stat().st_mtime)
    except Exception:
        return None
    return df if len(df) else None


def read_json(name):
    path = DATA / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def monthly(name):
    df = read_csv(name)
    if df is None:
        return None
    df["month"] = pd.to_datetime(df["month"])
    return df.sort_values("month").reset_index(drop=True)


def ago(iso):
    try:
        dt = datetime.fromisoformat(iso)
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    except Exception:
        return "date inconnue"
    if mins < 90:
        return f"il y a {max(mins, 0)} min"
    if mins < 60 * 48:
        return f"il y a {mins // 60} h"
    return f"il y a {mins // 1440} jours"


def fmt(n):
    return f"{n:,.0f}".replace(",", " ")


# ---------- Prévision avec marge d'incertitude (méthode du cours : erreur moyenne MAE) ----------
@st.cache_data(ttl=3600)
def forecast(values, index, horizon=FORECAST_MONTHS, test=6):
    s = pd.Series(values, index=pd.DatetimeIndex(index)).asfreq("MS")

    def fit(x):
        return ExponentialSmoothing(x, trend="add", damped_trend=True, seasonal="add",
                                    seasonal_periods=12).fit()

    try:
        pred_test = fit(s.iloc[:-test]).forecast(test)
        mae = float(np.mean(np.abs(pred_test.values - s.iloc[-test:].values)))
        fc = fit(s).forecast(horizon)
    except Exception:
        return None
    return fc.index.tolist(), fc.values.tolist(), mae


la = monthly("la_teu_monthly.csv")
lb = monthly("lb_teu_monthly.csv")
cppi = read_csv("cppi.csv")
unctad = read_csv("unctad.csv")
ais = read_json("ais.json")
meteo = read_json("weather.json")
ais_hist = read_csv("ais_history.csv")

st.markdown("""
<div class="hero">
  <div class="eyebrow">TABLEAU DE BORD PORTUAIRE · M2 IAMD · UNIVERSITÉ DE DJIBOUTI</div>
  <h1>San Pedro Bay : Los Angeles et Long Beach</h1>
  <p>Comment va le plus grand complexe portuaire des États-Unis, et comment se situe-t-il face aux autres ports, dont Djibouti ?
     Chaque tuile indique sa valeur, sa référence, sa tendance et sa date de mise à jour.</p>
  <span class="chip">👤 Pour : la direction d'un port ou d'un terminal</span>
  <span class="chip">🎯 Décision : ajuster la capacité (postes, équipes)</span>
  <span class="chip">🌍 Comparaison : CPPI 2024-2025 et CNUCED</span>
</div>
""", unsafe_allow_html=True)

# ---------- Calculs pour les tuiles ----------
tiles = []

# 1. Volume du dernier mois
if la is not None:
    last = la.iloc[-1]
    prev = la.iloc[-2]
    base = la.iloc[-13:-1]["total"].mean() if len(la) > 13 else np.nan
    lbl = "EVP Los Angeles"
    val = float(last["total"])
    if lb is not None and (lb["month"] == last["month"]).any():
        lbl = "EVP Los Angeles + Long Beach"
        val += float(lb.loc[lb["month"] == last["month"], "total"].iloc[0])
        prev_lb = lb.loc[lb["month"] == prev["month"], "total"]
        prev_val = float(prev["total"]) + (float(prev_lb.iloc[0]) if len(prev_lb) else np.nan)
        base_lb = lb[(lb["month"] < last["month"]) & (lb["month"] >= last["month"] - pd.DateOffset(months=12))]["total"]
        base = base + base_lb.mean() if len(base_lb) == 12 else np.nan
    else:
        prev_val = float(prev["total"])
    delta = (val / prev_val - 1) * 100 if prev_val == prev_val else None
    alert = base == base and val < VOLUME_ALERT * base
    ref = (f"Référence : moyenne des 12 mois précédents = {fmt(base)} · alerte si < {int(VOLUME_ALERT*100)} %"
           if base == base else "Référence : 12 mois précédents non disponibles")
    if lb is not None and "Long Beach" in lbl:
        both = la.merge(lb, on="month", suffixes=("_la", "_lb"))
        spark = (both["total_la"] + both["total_lb"]).tolist()[-24:]
    else:
        spark = la["total"].tolist()[-24:]
    tiles.append(dict(label=f"{lbl} ({last['month']:%m/%Y})", value=fmt(val),
                      delta=None if delta is None else f"{delta:+.1f} % vs mois précédent",
                      ref=ref, alert=alert, upd="Sites des ports · repris le 19/11/2026",
                      tag="VOLUME", thr=True, spark=spark))
else:
    tiles.append(dict(label="EVP du dernier mois", value="n/d", ref="Fichier la_teu_monthly.csv absent", alert=False, upd=""))

# 2. Variation sur 12 mois (Los Angeles)
if la is not None and len(la) >= 25:
    def var12(df):
        a = df["total"].iloc[-12:].sum()
        b = df["total"].iloc[-24:-12].sum()
        return (a / b - 1) * 100
    v = var12(la)
    v_before = var12(la.iloc[:-1])
    tiles.append(dict(label="Variation sur 12 mois (Los Angeles)", value=f"{v:+.1f} %",
                      delta=f"{v - v_before:+.1f} pt vs mois précédent",
                      ref="Référence : 0 % · alerte si négatif", alert=v < 0,
                      upd="Sites des ports · repris le 19/11/2026", tag="TENDANCE", thr=True))
else:
    tiles.append(dict(label="Variation sur 12 mois", value="n/d", ref="Pas assez de mois", alert=False, upd=""))

# 3. Rang CPPI de Djibouti
if cppi is not None and (cppi["port"] == "Djibouti").any():
    dj = cppi[cppi["port"] == "Djibouti"].copy()
    dj["an"] = dj["edition"].str.extract(r"(\d{4})").astype(int)
    dj = dj.sort_values("an")
    cur = dj.iloc[-1]
    d = None
    if len(dj) > 1:
        d = int(cur["rang"]) - int(dj.iloc[-2]["rang"])
    la_r = cppi[(cppi["port"] == "Los Angeles")]
    la_txt = ""
    if len(la_r):
        r = la_r.sort_values("edition").iloc[-1]
        la_txt = f" · Los Angeles : n° {int(r['rang'])} ({r['edition']})"
    tiles.append(dict(label=f"Rang CPPI de Djibouti ({cur['edition']})", value=f"n° {int(cur['rang'])}",
                      delta=None if d is None else f"{d:+d} places vs édition précédente",
                      delta_inverse=True,
                      ref="Référence : plus le rang est petit, mieux c'est" + la_txt,
                      alert=False, upd="Banque mondiale (annexe CPPI 2025) · 19/11/2026", tag="CLASSEMENT"))
else:
    tiles.append(dict(label="Rang CPPI de Djibouti", value="n/d", ref="Données CPPI absentes", alert=False, upd=""))

# 4. Temps médian au port (CNUCED)
if unctad is not None:
    t = unctad[unctad["indicateur"].str.contains("temps", case=False)]
    us = t[t["pays"] == "États-Unis"]
    if len(us):
        r = us.sort_values("annee").iloc[-1]
        jp = t[t["pays"] == "Japon"]
        jp_txt = f" · Japon : {jp.sort_values('annee').iloc[-1]['valeur']:.2f} j" if len(jp) else ""
        tiles.append(dict(label=f"Temps médian au port, États-Unis ({int(r['annee'])})",
                          value=f"{r['valeur']:.2f} j".replace(".", ","), delta=None,
                          ref="Référence : plus c'est court, mieux c'est" + jp_txt,
                          alert=False, upd="CNUCED via Statista · 19/11/2026", tag="TEMPS AU PORT"))
if len(tiles) < 4:
    tiles.append(dict(label="Temps médian au port (CNUCED)", value="n/d",
                      ref="Données CNUCED à ajouter dans data/clean/unctad.csv", alert=False, upd=""))

# 5. Navires AIS
if ais is not None:
    n = len(ais.get("ships", []))
    d = None
    if ais_hist is not None and len(ais_hist) >= 2:
        d = n - int(ais_hist["nb_ships"].iloc[-2])
    tiles.append(dict(label="Navires autour du port (AIS)", value=str(n),
                      delta=None if d is None else f"{d:+d} vs relevé précédent",
                      delta_inverse=True,
                      ref=f"Référence : alerte au-dessus de {AIS_CROWD_ALERT} navires (couverture gratuite limitée)",
                      alert=n > AIS_CROWD_ALERT, upd=f"aisstream.io · {ago(ais['fetched_at_utc'])}",
                      tag="EN DIRECT · AIS", thr=True,
                      spark=ais_hist["nb_ships"].tolist()[-24:] if ais_hist is not None and len(ais_hist) >= 2 else None))
else:
    tiles.append(dict(label="Navires autour du port (AIS)", value="n/d",
                      ref="Source AIS indisponible : lance scripts/fetch_ais.py", alert=False, upd=""))

# 6. Rafales prévues
gust_max = None
if meteo is not None:
    h = meteo["hourly"]
    g = [x for x in h["gust_kmh"][:24] if x is not None]
    gust_max = max(g) if g else None
if gust_max is not None:
    tiles.append(dict(label="Rafales maximales prévues (24 h)", value=f"{gust_max:.0f} km/h", delta=None,
                      ref=f"Référence : alerte au-dessus de {GUST_ALERT_KMH} km/h",
                      alert=gust_max > GUST_ALERT_KMH, upd=f"Open-Meteo · {ago(meteo['fetched_at_utc'])}",
                      tag="MÉTÉO", thr=True, spark=g))
else:
    tiles.append(dict(label="Rafales maximales prévues (24 h)", value="n/d",
                      ref="Source météo indisponible : lance scripts/fetch_meteo.py", alert=False, upd=""))

for row_no, row in enumerate((tiles[:3], tiles[3:])):
    cols = st.columns(3)
    for k, (col, t) in enumerate(zip(cols, row)):
        kind = "alert" if t["alert"] else "ok"
        with col.container(border=True, key=f"tile_{kind}_{row_no}{k}"):
            if t.get("tag"):
                st.markdown(f'<span class="tag">{t["tag"]}</span>', unsafe_allow_html=True)
            extra = {}
            if t.get("spark") and len(t["spark"]) > 2:
                extra = dict(chart_data=t["spark"], chart_type="area")
            st.metric(t["label"], t["value"], t.get("delta"),
                      delta_color="inverse" if t.get("delta_inverse") else "normal", **extra)
            if t.get("thr"):
                if t["alert"]:
                    st.markdown('<span class="pill alert">⚠ ALERTE : seuil dépassé</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span class="pill ok">✔ Dans la norme</span>', unsafe_allow_html=True)
            st.caption(t["ref"])
            if t["upd"]:
                st.caption(f"Mis à jour : {t['upd']}")

# ---------- Volumes + comparaison ----------
left, right = st.columns(2, gap="large")

with left:
    section(1, "Volumes mensuels (EVP)", "Los Angeles et Long Beach depuis 2019, avec prévision à 6 mois")
    if la is None:
        st.warning("Source indisponible : volumes de Los Angeles non trouvés (data/clean/la_teu_monthly.csv).")
    else:
        fig = go.Figure()
        fig.add_scatter(x=la["month"], y=la["total"], name="Los Angeles", mode="lines",
                        line=dict(color=BLUE, width=2.5))
        if lb is not None:
            fig.add_scatter(x=lb["month"], y=lb["total"], name="Long Beach", mode="lines",
                            line=dict(color=ORANGE, width=2.5))
        res = forecast(la["total"].tolist(), la["month"].tolist())
        mae = None
        if res:
            idx, fc, mae = res
            fc = np.array(fc)
            fig.add_shape(type="rect", xref="x", yref="paper", x0=idx[0], x1=idx[-1], y0=0, y1=1,
                          fillcolor="rgba(43,16,85,0.06)", line_width=0, layer="below")
            fig.add_annotation(x=idx[len(idx) // 2], y=1, yref="paper", text="prévision", showarrow=False,
                               font=dict(size=11, color="#6b5f85"), yanchor="bottom")
            fig.add_scatter(x=idx, y=fc, name="Prévision LA", mode="lines", line=dict(dash="dash", color=BLUE, width=2.5))
            fig.add_scatter(x=idx + idx[::-1], y=list(fc + mae) + list((fc - mae)[::-1]), fill="toself",
                            mode="lines", line=dict(width=0), fillcolor="rgba(98,80,214,0.18)",
                            name="Prévision ± erreur moyenne", hoverinfo="skip")
        style_fig(fig, 360)
        fig.update_layout(yaxis_title="EVP par mois", margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width="stretch")
        if res:
            st.caption(f"Prévision de Los Angeles à {FORECAST_MONTHS} mois (lissage exponentiel saisonnier). "
                       f"Erreur moyenne du modèle sur les 6 derniers mois : {fmt(mae)} EVP. "
                       "La zone violette montre prévision ± cette erreur.")
        else:
            st.warning("La prévision n'a pas pu être calculée.")
        if lb is None:
            st.warning("Source indisponible : volumes de Long Beach non trouvés.")
        elif lb["month"].min() > pd.Timestamp("2019-12-31"):
            st.info(f"Long Beach : données partielles (depuis {lb['month'].min():%m/%Y}). "
                    "Voir scripts/clean_polb.py pour ajouter 2019-2025.")

        # Détail du dernier mois : import, export, vides, total
        rows = []
        for name, df in (("Los Angeles", la), ("Long Beach", lb)):
            if df is not None:
                r = df.iloc[-1]
                rows.append({"Port": name, "Mois": f"{r['month']:%m/%Y}", "Import": fmt(r["imports"]),
                             "Export": fmt(r["exports"]), "Vides": fmt(r["empties"]), "Total": fmt(r["total"])})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            comp = go.Figure()
            ports = [r["Port"] for r in rows]
            for key, name, color in (("imports", "Import", "#4a3aa7"), ("exports", "Export", "#9085e9"),
                                     ("empties", "Vides", "#dcd8f8")):
                vals = [float(df.iloc[-1][key]) for nm, df in (("Los Angeles", la), ("Long Beach", lb)) if df is not None]
                comp.add_bar(y=ports, x=vals, name=name, orientation="h", marker_color=color,
                             text=[f"{v/1000:,.0f} k".replace(",", " ") for v in vals], textposition="inside",
                             marker_line=dict(color="#f7f3fb", width=2))
            style_fig(comp, 220)
            comp.update_layout(barmode="stack", xaxis_title="EVP du dernier mois", yaxis=dict(autorange="reversed"),
                               legend=dict(orientation="h", y=1.25, traceorder="normal"),
                               margin=dict(l=10, r=10, t=40, b=10))
            st.caption("Composition du dernier mois : import, export et conteneurs vides (EVP).")
            st.plotly_chart(comp, width="stretch")

with right:
    section(2, "Comparaison mondiale", "CPPI (Banque mondiale) et temps au port (CNUCED)")
    if cppi is None:
        st.warning("Source indisponible : données CPPI non trouvées (data/clean/cppi.csv).")
    else:
        pivot = cppi.pivot_table(index="port", columns="edition", values="rang", aggfunc="first")
        pivot = pivot.reindex(sorted(pivot.columns), axis=1)
        pivot["_best"] = pivot.min(axis=1)
        pivot = pivot.sort_values("_best").drop(columns="_best")
        st.caption("Rang CPPI par édition (1 = meilleur). 1 = meilleur port.")
        st.dataframe(pivot.fillna("").astype(object).map(lambda x: f"n° {int(x)}" if x != "" else ""),
                     width="stretch")
        if cppi["score"].notna().any():
            score = cppi.pivot_table(index="port", columns="edition", values="score", aggfunc="first")
            score = score.reindex(index=pivot.index, columns=pivot.columns)
            st.caption("Score CPPI (0 = moyenne mondiale de 2024 ; plus haut = navires qui passent moins de temps au port).")
            st.dataframe(score.round(0).astype("Int64"), width="stretch")
        last_ed = cppi.copy()
        last_ed["an"] = last_ed["edition"].str.extract(r"(\d{4})").astype(int)
        latest = last_ed.sort_values("an").groupby("port").tail(1).sort_values("rang")
        latest["label"] = latest["port"] + " (" + latest["edition"] + ")"
        colors = [ORANGE if p == "Djibouti" else GREY for p in latest["port"]]
        bar = go.Figure(go.Bar(x=latest["rang"], y=latest["label"], orientation="h", marker_color=colors,
                               text=[f"n° {int(r)}" for r in latest["rang"]], textposition="outside",
                               cliponaxis=False))
        style_fig(bar, 300)
        bar.update_layout(xaxis_title="Rang (plus petit = mieux)", yaxis=dict(autorange="reversed"),
                          margin=dict(l=10, r=40, t=10, b=10))
        st.plotly_chart(bar, width="stretch")
    st.markdown("**Temps médian au port, porte-conteneurs (CNUCED)**")
    if unctad is None:
        st.warning("Source indisponible : données CNUCED non trouvées (data/clean/unctad.csv).")
    else:
        st.dataframe(unctad[["pays", "annee", "indicateur", "valeur", "unite"]], hide_index=True,
                     width="stretch")
        if not (unctad["pays"] == "Djibouti").any():
            st.info("Djibouti : non disponible. Le tableau d'escales de la CNUCED (UNCTADstat) ne publie pas Djibouti, "
                    "et son profil pays n'a pas de section « Port calls and performance ».")
    st.caption("Attention : le CPPI est un score par port ; la CNUCED donne des chiffres par pays. "
               "Ce sont deux mesures différentes, à ne pas additionner ni mélanger.")

# ---------- En direct ----------
section(3, "En direct : navires et météo du port", "Navires captés par AIS et prévision du vent, des rafales et des vagues")
c1, c2 = st.columns(2)
with c1:
    if ais is None or not ais.get("ships"):
        st.warning("Source AIS indisponible ou vide. Lance scripts/fetch_ais.py (clé aisstream.io dans .env). "
                   "La couverture gratuite peut être faible.")
    else:
        ships = pd.DataFrame(ais["ships"]).rename(columns={"lat": "latitude", "lon": "longitude"})
        st.map(ships[["latitude", "longitude"]], zoom=10, color=RED, size=140)
        st.caption(f"{len(ships)} navires vus pendant {ais.get('listen_seconds', '?')} s · {ago(ais['fetched_at_utc'])}")
        show = ships[[c for c in ["name", "type", "status", "speed_kn"] if c in ships.columns]].rename(
            columns={"name": "Nom", "type": "Type", "status": "Statut", "speed_kn": "Vitesse (nœuds)"})
        st.dataframe(show, hide_index=True, width="stretch", height=180)
with c2:
    if meteo is None:
        st.warning("Source météo indisponible. Lance scripts/fetch_meteo.py (Open-Meteo, sans clé).")
    else:
        cur = meteo["current"]
        h = meteo["hourly"]
        wave_by_time = dict(zip(h["wave_time"], h["wave_m"]))
        rows = [{"Moment": "Maintenant", "Vent (km/h)": cur["wind_kmh"], "Rafales (km/h)": cur["gust_kmh"],
                 "Vagues (m)": cur.get("wave_m")}]
        for k in (6, 12, 24):
            if k < len(h["time"]):
                rows.append({"Moment": f"+{k} h", "Vent (km/h)": h["wind_kmh"][k], "Rafales (km/h)": h["gust_kmh"][k],
                             "Vagues (m)": wave_by_time.get(h["time"][k])})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(f"Open-Meteo · {ago(meteo['fetched_at_utc'])}")
        waves = [w for w in h["wave_m"][:24] if w is not None]
        wave_max = max(waves) if waves else None
        problems = []
        if gust_max is not None and gust_max > GUST_ALERT_KMH:
            problems.append(f"rafales jusqu'à {gust_max:.0f} km/h (seuil {GUST_ALERT_KMH})")
        if wave_max is not None and wave_max > WAVE_ALERT_M:
            problems.append(f"vagues jusqu'à {wave_max:.1f} m (seuil {WAVE_ALERT_M})")
        if problems:
            st.error("Alerte météo : " + " ; ".join(problems) + ".")
        else:
            st.success(f"Aucune alerte météo : rafales sous {GUST_ALERT_KMH} km/h et vagues sous {WAVE_ALERT_M} m sur 24 h.")

# ---------- Recommandation ----------
section(4, "Recommandation d'action", "Ce que le tableau de bord suggère, un humain valide")
reco = []
if la is not None:
    res = forecast(la["total"].tolist(), la["month"].tolist())
    if res:
        idx, fc, mae = res
        recent = la["total"].iloc[-6:].mean()
        change = (np.mean(fc) / recent - 1) * 100
        if change > 5:
            reco.append(f"Volumes prévus en hausse de {change:.0f} % sur {FORECAST_MONTHS} mois (± {fmt(mae)} EVP par mois) : "
                        "prévoir des équipes et des postes à quai supplémentaires aux mois de pointe.")
        elif change < -5:
            reco.append(f"Volumes prévus en baisse de {abs(change):.0f} % sur {FORECAST_MONTHS} mois (± {fmt(mae)} EVP par mois) : "
                        "alléger le planning des quais et programmer la maintenance sur ces mois creux.")
        else:
            reco.append(f"Volumes prévus stables ({change:+.0f} %) : garder le planning actuel et surveiller la tuile de volume.")
if gust_max is not None and gust_max > GUST_ALERT_KMH:
    reco.append("Rafales élevées prévues : préparer l'arrêt possible des grues et décaler les opérations sensibles.")
if ais is not None and len(ais.get("ships", [])) > AIS_CROWD_ALERT:
    reco.append("Beaucoup de navires dans la zone : vérifier les créneaux d'accostage avec la capitainerie.")
if reco:
    for r in reco:
        st.info(r)
    st.caption("Niveau d'automatisation 3 : le tableau de bord recommande, le responsable d'exploitation valide ou refuse. "
               "La prévision a une marge d'erreur : à confronter à l'avis de l'équipe.")
else:
    st.warning("Pas assez de données pour proposer une recommandation.")

# ---------- Sources ----------
with st.expander("Sources, dates de récupération et limites"):
    sp = ROOT / "sources.csv"
    if sp.exists():
        st.dataframe(pd.read_csv(sp), hide_index=True, width="stretch")
    st.caption("Détails de la méthode et des limites dans le README.")

st.markdown(
    '<div class="foot">Projet noté M2 IAMD · Séquence 6, partie 2 · Université de Djibouti. '
    'Les seuils d\'alerte sont des choix de l\'auteur, à valider avec un responsable d\'exploitation. '
    'Sources et méthode : voir le tableau ci-dessus et le README.</div>', unsafe_allow_html=True)
