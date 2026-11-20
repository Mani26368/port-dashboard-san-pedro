# Tableau de bord portuaire : San Pedro Bay (Los Angeles + Long Beach)

Exercice noté, séquence 6 partie 2 (tableaux de bord intelligents et aide à la décision).
Outil : Streamlit (Python). Une seule page, comme demandé par le cours (un écran unique).

## Lancer

```bash
pip install -r requirements.txt
streamlit run app.py
```

L'appli lit seulement les fichiers de `data/clean/`. Elle n'appelle aucune API et ne contient aucune clé.

## Mettre à jour le direct (AIS et météo)

```bash
python scripts/fetch_meteo.py        # Open-Meteo, sans clé
python scripts/fetch_ais.py 30       # aisstream.io, écoute 30 secondes
```

Pour l'AIS : crée une clé gratuite sur aisstream.io, copie `.env.example` en `.env` et mets la clé dedans.
Le fichier `.env` est dans `.gitignore` : il ne doit jamais être envoyé ni rendu.
Tu peux lancer ces scripts toutes les heures avec une tâche planifiée (cron).
Si une source ne répond pas, le script garde l'ancien fichier et l'appli affiche un message clair.

## Sources (adresses et dates dans `sources.csv`)

| Donnée | Source | État |
|---|---|---|
| Volumes de Los Angeles 2019-2026 | Site du Port of Los Angeles (pages Historical TEU Statistics) | Complet, repris le 19/11/2026 |
| Volumes de Long Beach | Site du Port of Long Beach, fichier « TEU Archive Since 1995 » (téléchargé le 20/11/2026) | Complet : 2019 à octobre 2026 |
| CPPI (score et rang) | Banque mondiale et S&P Global, fichier Annex du CPPI 2025 | Complet pour 8 ports, éditions 2024 et 2025 |
| Escales et temps médian | CNUCED (UNCTADstat) | Partiel : escales 2023 (4 pays) ; temps médian 2021 (2 pays) ; Djibouti absent |
| Navires en direct | aisstream.io | Par script |
| Vent, rafales, vagues | Open-Meteo | Par script |

## Traitements

- **CPPI** : ports choisis pour la comparaison : Los Angeles, Long Beach, Djibouti, Fuzhou (n° 1 mondial), Singapour, Jebel Ali (région) et Philadelphie (meilleur port américain), plus Salalah.

- **Vides (Los Angeles)** : le site donne import, export et total. Les vides sont calculés : total − import − export.
  Le calcul retombe sur les chiffres publiés par le port (septembre 2026 : 371 206 ; octobre 2026 : 373 271).
- **Novembre 2020 (Los Angeles)** : la page affiche `889.,748.15` (faute de frappe sur le site). Le fichier utilise 889 748,15. À vérifier.
- **Long Beach** : `scripts/clean_polb.py` transforme le tableau d'archive du port en CSV propre (voir le début du script).
- Les mois sont des mois civils ; l'unité est l'EVP (conteneur équivalent 20 pieds).

## Méthode des fonctions intelligentes

1. **Prévision avec marge d'incertitude** (Los Angeles, 6 mois) : lissage exponentiel avec tendance amortie et saison de 12 mois (`statsmodels`).
   La marge vient de l'erreur moyenne (MAE) : le modèle est ajusté sans les 6 derniers mois, il prédit ces 6 mois,
   et on mesure l'écart moyen avec la réalité. La zone affichée est prévision ± cette erreur.
2. **Alerte météo** : rafales > 50 km/h ou vagues > 2,5 m sur 24 h. Ces seuils sont des choix de l'auteur, à ajuster et à justifier.
3. **Alerte de volume** : mois sous 90 % de la moyenne des 12 mois précédents.
4. **Recommandation** : règles simples qui lisent la prévision, la météo et le nombre de navires.
   Niveau d'automatisation 3 : le tableau de bord recommande, une personne valide.

## Limites (à dire à l'oral)

- Le CPPI est un score par port, la CNUCED donne des chiffres par pays : deux mesures différentes, jamais additionnées.
- CPPI : les rangs et scores viennent du fichier Annex officiel (400 ports en 2025). Le rang 2025 est celui de l'annexe.
  Le rang 2024 est recalculé à partir des scores 2024 de l'annexe (403 ports, comme l'édition 2024). Les scores des années 2020 à 2023 existent dans l'annexe mais ne sont pas utilisés.
  Le score est comparable d'une année à l'autre : 0 = moyenne mondiale de 2024. Le CPPI mesure le temps des navires au port, pas le volume.
- CNUCED : Djibouti n'apparaît pas dans le tableau d'escales d'UNCTADstat (US.PortCallsArrivals, 87 lignes, téléchargé le 20/11/2026), et son profil pays n'a pas de section « Port calls and performance ». Le nombre d'escales et le temps médian de Djibouti sont donc indisponibles ; le tableau de bord l'indique. Affichés : nombre d'escales de porte-conteneurs 2023 (États-Unis, Chine, Japon, Singapour) et temps médian 2021 (États-Unis, Japon, via Statista). Le tableau du temps médian de la CNUCED n'a pas été obtenu.
- Long Beach : le site polb.com était bloqué (« Access Denied ») depuis Djibouti le 19/11/2026. Les données ont été téléchargées le 20/11/2026 via un VPN. Les vides de Long Beach = vides entrants + sortants.
- La couverture AIS gratuite peut être faible, surtout loin de Los Angeles : le nombre de navires est un minimum.
- La prévision est une extrapolation des mois passés : elle ne connaît ni les grèves, ni les droits de douane, ni les crises.
- Les seuils d'alerte ne sont pas ceux d'une vraie capitainerie.

## Présentation

Une seule page, comme le demande le cours : bandeau de titre (pour qui, quelle décision), 6 tuiles (valeur, référence, tendance, date, alerte), puis volumes + prévision, comparaison mondiale, vue en direct (AIS + météo), recommandation et sources. Couleurs : violet = Los Angeles, rose = Long Beach, rouge = alerte. Le thème est dans `.streamlit/config.toml` et les styles dans le début de `app.py`.

## Fichiers

```
app.py                    la page Streamlit
scripts/fetch_meteo.py    météo → data/clean/weather.json
scripts/fetch_ais.py      AIS → data/clean/ais.json
scripts/clean_polb.py     Long Beach → data/clean/lb_teu_monthly.csv
data/clean/               fichiers lus par l'appli
sources.csv               adresses et dates de récupération
```
