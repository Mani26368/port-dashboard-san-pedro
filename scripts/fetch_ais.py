"""Écoute le flux AIS (aisstream.io) autour du port pendant quelques secondes
et enregistre les navires vus dans data/clean/ais.json.

Il faut une clé gratuite sur aisstream.io, mise dans le fichier .env (jamais dans le code) :
    AISSTREAM_API_KEY=ta_cle
Lancer :  python scripts/fetch_ais.py          (30 secondes d'écoute par défaut)
          python scripts/fetch_ais.py 60       (60 secondes)
"""
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import websockets
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "clean" / "ais.json"
HISTORY = ROOT / "data" / "clean" / "ais_history.csv"
# Zone autour de la baie de San Pedro : [[lat1, lon1], [lat2, lon2]]
BOX = [[33.55, -118.45], [33.85, -118.00]]

# Codes de statut de navigation AIS les plus courants
NAV_STATUS = {0: "en route (moteur)", 1: "au mouillage", 2: "sans maîtrise", 3: "manœuvrabilité restreinte",
              5: "amarré", 6: "échoué", 8: "à la voile", 15: "non défini"}


def ship_type_label(code):
    if code is None:
        return "inconnu"
    if 70 <= code <= 79:
        return "cargo / porte-conteneurs"
    if 80 <= code <= 89:
        return "pétrolier / tanker"
    if 60 <= code <= 69:
        return "passagers"
    if code == 52:
        return "remorqueur"
    if code == 31 or code == 32:
        return "remorqueur"
    return f"autre ({code})"


async def listen(seconds, key):
    ships = {}
    sub = {"APIKey": key, "BoundingBoxes": [BOX], "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}
    async with websockets.connect("wss://stream.aisstream.io/v0/stream", open_timeout=40) as ws:
        await ws.send(json.dumps(sub))  # à envoyer dans les 3 secondes
        end = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=end - asyncio.get_event_loop().time())
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            meta = msg.get("MetaData", {})
            mmsi = meta.get("MMSI")
            if mmsi is None:
                continue
            ship = ships.setdefault(mmsi, {"mmsi": mmsi})
            ship["name"] = (meta.get("ShipName") or ship.get("name") or "").strip()
            if msg.get("MessageType") == "PositionReport":
                pr = msg["Message"]["PositionReport"]
                ship["lat"] = meta.get("latitude", pr.get("Latitude"))
                ship["lon"] = meta.get("longitude", pr.get("Longitude"))
                ship["status"] = NAV_STATUS.get(pr.get("NavigationalStatus"), "autre")
                ship["speed_kn"] = pr.get("Sog")
            elif msg.get("MessageType") == "ShipStaticData":
                ship["type"] = ship_type_label(msg["Message"]["ShipStaticData"].get("Type"))
    return [s for s in ships.values() if "lat" in s]


def main():
    load_dotenv(ROOT / ".env")
    key = os.environ.get("AISSTREAM_API_KEY")
    if not key:
        print("Clé absente : mets AISSTREAM_API_KEY dans le fichier .env", file=sys.stderr)
        sys.exit(1)
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    try:
        ships = asyncio.run(listen(seconds, key))
    except Exception as exc:
        print(f"Source AIS indisponible : {exc}. Ancien fichier conservé.", file=sys.stderr)
        sys.exit(1)
    for s in ships:
        s.setdefault("type", "inconnu")
        s.setdefault("status", "inconnu")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"fetched_at_utc": now, "listen_seconds": seconds, "ships": ships}, ensure_ascii=False))
    new = not HISTORY.exists()
    with HISTORY.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["fetched_at_utc", "nb_ships"])
        w.writerow([now, len(ships)])
    print(f"{len(ships)} navires enregistrés dans {OUT}")


if __name__ == "__main__":
    main()
