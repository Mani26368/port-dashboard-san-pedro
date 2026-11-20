"""Récupère la météo du port (Open-Meteo, sans clé) et l'enregistre dans data/clean/weather.json.

À lancer à la main ou toutes les heures (cron / tâche planifiée) :  python scripts/fetch_meteo.py
Le tableau de bord lit ce fichier : il n'appelle jamais l'API lui-même.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "clean" / "weather.json"
# Entrée de la baie de San Pedro (près des brise-lames)
LAT, LON = 33.70, -118.25
TZ = "America/Los_Angeles"


def get(url, params):
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    try:
        wind = get(
            "https://api.open-meteo.com/v1/forecast",
            {
                "latitude": LAT, "longitude": LON, "timezone": TZ, "forecast_days": 2,
                "wind_speed_unit": "kmh",
                "current": "wind_speed_10m,wind_gusts_10m",
                "hourly": "wind_speed_10m,wind_gusts_10m",
            },
        )
        waves = get(
            "https://marine-api.open-meteo.com/v1/marine",
            {
                "latitude": LAT, "longitude": LON, "timezone": TZ, "forecast_days": 2,
                "current": "wave_height",
                "hourly": "wave_height",
            },
        )
    except Exception as exc:  # source indisponible : on garde l'ancien fichier
        print(f"Source météo indisponible : {exc}. Ancien fichier conservé.", file=sys.stderr)
        sys.exit(1)

    out = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "location": {"lat": LAT, "lon": LON},
        "current": {
            "time": wind["current"]["time"],
            "wind_kmh": wind["current"]["wind_speed_10m"],
            "gust_kmh": wind["current"]["wind_gusts_10m"],
            "wave_m": waves.get("current", {}).get("wave_height"),
        },
        "hourly": {
            "time": wind["hourly"]["time"],
            "wind_kmh": wind["hourly"]["wind_speed_10m"],
            "gust_kmh": wind["hourly"]["wind_gusts_10m"],
            "wave_time": waves["hourly"]["time"],
            "wave_m": waves["hourly"]["wave_height"],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False))
    print("Météo enregistrée :", OUT)


if __name__ == "__main__":
    main()
