# Plateforme de tourisme ferroviaire — socle du projet

Prototype pour trouver des sorties accessibles en train en Auvergne-Rhône-Alpes :
on explore les gares et leurs points d'intérêt sur une carte, ou on formule sa demande en langage naturel.

Ce dépôt contient le socle posé le lundi : la chaîne de données, l'API métier, une première brique d'IA et l'interface.

## Ce qui fonctionne

- **Ingestion** de trois sources ouvertes (gares SNCF, horaires GTFS SNCF, points d'intérêt DATAtourisme) : nettoyage, normalisation, rapprochement, chargement dans PostGIS.
- **API métier sans LLM** : recherche de gares, points d'intérêt à distance de marche, destinations accessibles depuis une gare, classement expliqué.
- **Recherche en langage naturel** : extraction des critères (par LLM si configuré, sinon par règles), mémoire de conversation, réponse rédigée à partir des seuls résultats de la base.
- **Interface** Next.js + Leaflet : onglets « Demander » et « Explorer », carte synchronisée avec les recommandations.

## Démarrage avec Docker seul

Prérequis : Docker Desktop démarré. Rien d'autre à installer.

```bash
# 1. Base, API et interface (le premier lancement télécharge les images : quelques minutes)
docker compose up -d --build

# 2. Données : d'abord le jeu d'essai (hors ligne, quelques secondes)...
docker compose run --rm api python -m ingestion.pipeline --exemple
# ... puis les vraies données (télécharge environ 50 Mo, à faire avant toute démonstration)
docker compose run --rm api python -m ingestion.pipeline --telecharger

# 3. Tests
docker compose run --rm api pytest
```

- API : http://localhost:8000/docs
- Interface : http://localhost:3000 (suivre son démarrage avec `docker compose logs -f web`, jusqu'à « Ready »)

Le code du backend et de l'interface est monté dans les conteneurs : une modification est prise en compte sans reconstruire.
Pour tout arrêter : `docker compose down`.

## Démarrage sans Docker pour l'API et l'interface

Prérequis : Docker (pour la base), Python 3.10 ou plus, Node.js 20 ou plus.

```bash
# 1. Base de données PostGIS
docker compose up -d db

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

# 3. Données
python -m ingestion.pipeline --exemple
python -m ingestion.pipeline --telecharger

# 4. API : http://localhost:8000/docs
uvicorn app.main:app --reload

# 5. Interface, dans un autre terminal, depuis la racine du projet : http://localhost:3000
cd web
npm install
npm run dev
```

Le pipeline affiche un bilan à chaque étape : gares retenues, arrêts GTFS rattachés, liaisons calculées,
points d'intérêt écartés, types DATAtourisme restés sans thème. **Lisez-le au premier chargement réel** (voir « Limites »).

## Brancher un LLM (facultatif)

Sans configuration, l'application fonctionne sans LLM : extraction par règles et réponses par gabarit.
Pour brancher un modèle, copier `.env.exemple` en `.env` et renseigner `LLM_BASE_URL`, `LLM_MODEL` et au besoin `LLM_API_KEY`.

Toute API compatible « OpenAI chat completions » convient : Ollama en local, ou un fournisseur cloud.
Passer de l'un à l'autre ne demande aucun changement de code, ce qui permet de comparer les deux avec le même script :

```bash
python -m evaluation.evaluer --csv resultats-local.csv      # avec le LLM configuré
python -m evaluation.evaluer --sans-llm                     # point de comparaison : règles seules
```

Le script rejoue les requêtes de `evaluation/requetes.json` et mesure la compréhension de la demande,
le respect des contraintes, le temps de réponse et les jetons consommés.

## Architecture

```
Sources ouvertes              ingestion/ (Python, pandas)              PostgreSQL + PostGIS
  SNCF gares (JSON)    ──►  nettoyage, normalisation        ──►   gare, gare_uic
  GTFS SNCF (zip)      ──►  liaisons directes entre gares   ──►   liaison ─► accessibilite (SQL)
  DATAtourisme (CSV)   ──►  thèmes internes                 ──►   poi ─► gare_poi (PostGIS)

Question ──► app/ia : critères (LLM ou règles) ──► app/metier : recherche SQL + classement
                                                            │
Interface Next.js + Leaflet ◄── API FastAPI ◄── app/ia : rédaction (LLM ou gabarits)
```

Le LLM n'intervient qu'aux deux extrémités : il traduit la question en critères, puis rédige à partir de résultats déjà choisis.
Il ne sélectionne jamais une destination et ne voit jamais la base.

| Dossier | Rôle |
| --- | --- |
| `db/schema.sql` | Schéma PostGIS, appliqué automatiquement par le pipeline |
| `backend/ingestion/` | Acquisition, nettoyage, normalisation, rapprochement, chargement |
| `backend/app/metier/` | Requêtes et classement, sans LLM |
| `backend/app/ia/` | Critères, extraction, client LLM, rédaction, orchestration |
| `backend/app/main.py` | Points d'accès de l'API |
| `backend/evaluation/` | Requêtes de test et script de mesure |
| `backend/tests/` | Tests automatiques |
| `web/` | Interface Next.js + Leaflet |
| `donnees/exemple/` | Jeu d'essai fictif, au format des vraies sources |

## API

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| GET | `/gares?q=` | Gares de la région, filtrables par nom |
| GET | `/gares/{id}/poi?theme=&marche_max=` | Points d'intérêt à distance de marche d'une gare |
| GET | `/destinations?origine=&duree_max=&marche_max=&theme=` | Destinations accessibles, classées, sans LLM |
| POST | `/recherche` | Recherche en langage naturel |
| GET | `/stats` | Volumes chargés et journal des imports |
| GET | `/themes`, `/sante` | Thèmes disponibles, état du service |

## Tests

```bash
cd backend
pytest                      # 53 tests sans base ni réseau
```

Les tests de la chaîne complète (16 de plus) ont besoin d'une base dédiée, **dont le contenu est effacé à chaque exécution** :

```bash
docker compose exec db createdb -U tourisme tourisme_test
# avec Docker seul
docker compose run --rm -e DATABASE_URL_TEST=postgresql://tourisme:tourisme@db:5432/tourisme_test api pytest
# sans Docker pour l'API
DATABASE_URL_TEST=postgresql://tourisme:tourisme@localhost:5432/tourisme_test pytest
```

## Hypothèses à connaître

Toutes sont regroupées dans `backend/app/config.py` et `backend/app/metier/scoring.py`.

- **Temps de trajet** : durée médiane des trains directs entre deux gares, calculée sur les horaires théoriques.
- **Correspondances** : une au maximum. La durée est une estimation (somme des deux tronçons + 15 min), sans tenir compte des horaires réels. L'interface le signale.
- **Marche depuis la gare** : distance à vol d'oiseau × 1,3, à 4,5 km/h. Ce n'est pas un itinéraire piéton.
- **Rattachement gare / point d'intérêt** : rayon de 2 km.
- **Thèmes** : déduits des types DATAtourisme par mots-clés (`backend/app/themes.py`), complétés par quelques mots du nom et de la description.
- **Classement** : thèmes couverts 35 %, nombre de lieux 20 %, trajet 20 %, marche 15 %, fréquence 10 %, moins 10 points par correspondance.

## Limites

- **L'ingestion a tourné sur les données réelles le 5 octobre 2026** (329 gares, 5 816 liaisons directes, 58 362 points d'intérêt), sans correction des lecteurs.
  Si un export change de format, les lecteurs retrouvent les colonnes par mots-clés ; sinon, ajuster `_champ(...)` dans `gares_sncf.py` ou `EN_TETES` dans `poi_datatourisme.py`.
- **Les événements ne sont pas filtrés par date** : ils sont écartés des recherches sans thème, et signalés quand ils sont demandés.
- **Les fichiers Docker et les requêtes PostGIS ont été validés sur la machine d'un membre du groupe**, pas dans une intégration continue.
- **Le chemin LLM a été testé avec un serveur simulé**, pas avec un vrai modèle.
- **L'interface n'a pas de tests automatiques** : elle se vérifie à la main dans un navigateur.
- **La difficulté des randonnées n'existe pas** dans l'export CSV de DATAtourisme : le critère est compris, signalé à l'utilisateur, et non appliqué.
- **Le thème « montagne » repose sur peu d'indices** : à vérifier sur les données réelles.
- **Pas de tracé des lignes ferroviaires** : la carte relie départ et destinations par des traits schématiques.
- **Les règles d'extraction ont été écrites à partir des requêtes du sujet** : leur score sur ces mêmes requêtes ne prouve rien. Ajoutez des requêtes nouvelles dans `evaluation/requetes.json`.
