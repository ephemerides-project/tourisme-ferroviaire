# Guide du code — Plateforme de tourisme ferroviaire

5 octobre 2026 · Hugo

L'idée à retenir tient en une phrase : les données et le classement vivent dans une couche métier en Python et SQL, et le LLM n'intervient qu'aux deux bouts, pour traduire la question en critères puis pour rédiger. Ce guide suit le code dans l'ordre où il s'exécute, pour que chacun puisse l'expliquer.

Les choix techniques, les sources de données et le plan de travail sont dans le [document de cadrage](CADRAGE.md).

## Carte du dépôt

Le dépôt se lit en quatre blocs : les données, la couche métier, l'IA, l'interface.

| Emplacement | Ce qu'on y trouve |
| --- | --- |
| `db/schema.sql` | Les sept tables PostGIS, créées automatiquement par le pipeline |
| `backend/ingestion/` | La chaîne de données : télécharger, nettoyer, croiser, charger |
| `backend/app/metier/` | Recherche et classement des destinations, sans aucun LLM |
| `backend/app/ia/` | Critères, extraction (LLM ou règles), rédaction, orchestration |
| `backend/app/main.py` | Les points d'accès de l'API FastAPI |
| `backend/app/themes.py` | La correspondance entre types DATAtourisme et thèmes internes |
| `backend/app/config.py` | Toutes les hypothèses réglables : rayon, vitesse de marche, valeurs par défaut |
| `backend/evaluation/` | Les 21 requêtes de test et le script de mesure |
| `backend/tests/` | 69 tests automatiques |
| `web/` | L'interface Next.js et la carte Leaflet |
| `donnees/` | Un jeu d'essai fictif, et les fichiers téléchargés (non versionnés) |
| `docker-compose.yml` | Les trois services : base, API, interface |

Deux règles tiennent tout le code ensemble :

- `metier/` n'importe jamais `ia/`. La couche métier fonctionne seule, ce que demande le sujet.
- Les constantes sont regroupées dans `config.py` et `scoring.py`. Aucun chiffre magique n'est caché dans une requête.

## L'ingestion, étape par étape

Une seule commande, `python -m ingestion.pipeline`, enchaîne quatre étapes et affiche un bilan à chacune. Le chef d'orchestre est la fonction `executer` de `pipeline.py`.

| Étape | Fichier | Ce que fait le code | Résultat du 5 octobre |
| --- | --- | --- | --- |
| 1. Gares | `gares_sncf.py` | `normaliser_gares` lit l'export SNCF, retrouve chaque champ par mots-clés et garde les gares dont le code INSEE commence par un département de la région | 2 792 lues, 329 retenues |
| 2. Horaires | `gtfs.py` | `rattacher_arrets` relie chaque arrêt GTFS à une gare ; `calculer_liaisons` en déduit durée, fréquence et tracé entre gares | 1 020 arrêts rattachés, 5 816 liaisons directes entre 328 gares |
| 3. Points d'intérêt | `poi_datatourisme.py`, `themes.py` | `normaliser_poi` écarte les lignes sans position, hors région ou en double, puis attribue les thèmes | 59 552 lus, 58 362 retenus |
| 2 bis. Voies (facultatif) | `voies.py` | `lire_lignes_sncf` construit le graphe du réseau ferré (fichier SNCF) ; `suivre` fait passer chaque tracé par ces lignes | à relever au premier lancement avec `--voies` |
| 4. Chargement | `charger.py` | Insertion en masse, puis `enrichir` calcule les rapprochements en SQL | 21 295 liens gare / lieu, 26 241 trajets à une correspondance |

### Le rapprochement gares / arrêts

Les deux sources ne partagent pas d'identifiant commun. `rattacher_arrets` procède en deux temps :

1. Le code UIC de la gare figure à la fin de l'identifiant d'arrêt SNCF (`StopPoint:OCETrain TER-87747006`). 954 arrêts sont rattachés ainsi.
2. À défaut, l'arrêt est rattaché à la gare la plus proche à moins de 300 m. 66 arrêts le sont ainsi.

Les arrêts hors région ne sont rattachés à rien : c'est ce qui filtre le flux national.

### Le calcul des liaisons

C'est le cœur de `gtfs.py`, dans `calculer_liaisons` :

1. Garder les trains (type de ligne 2) et leurs passages dans les gares de la région.
2. Convertir les heures en minutes. Le GTFS écrit « 25:10:00 » pour un passage après minuit, d'où la fonction `heure_en_minutes`.
3. Joindre la table des passages avec elle-même sur l'identifiant du train : chaque couple montée / descente donne une durée.
4. Regrouper par couple de gares : durée médiane, et nombre de trains par jour.

La médiane est préférée au minimum pour ne pas promettre le temps d'un train exceptionnel.

### Les thèmes

DATAtourisme décrit chaque lieu par des types (`Museum`, `WalkingTour`). `themes.py` les ramène à dix thèmes, de trois façons :

- `MOTS_CLES` : un thème est attribué si un mot-clé apparaît dans le nom du type.
- `TYPES_EXACTS` : pour les noms courts, où un mot-clé serait trop large (`Park` attraperait `Parking`).
- `enrichir_par_texte` : quelques mots du nom et de la description ajoutent montagne, randonnée, famille ou gastronomie.

Environ 15 % des lieux restent sans thème. Ce sont des commerces et des services, listés dans `TYPES_SANS_THEME` et écartés volontairement.

## La base

Sept tables, dont trois calculées à l'ingestion pour que chaque recherche reste une simple jointure.

| Table | Contenu | Remplie par |
| --- | --- | --- |
| `gare` | Gares de la région et leur position | Étape 1 |
| `gare_uic` | Codes UIC de chaque gare | Étape 1 |
| `liaison` | Durée médiane, trains par jour et tracé (colonne `trace`) entre deux gares, en direct | Étape 2 |
| `poi` | Points d'intérêt, thèmes internes et types d'origine | Étape 3 |
| `gare_poi` | Distance et minutes de marche entre une gare et un lieu | `enrichir`, en SQL |
| `accessibilite` | Trajet direct, ou meilleur trajet à une correspondance | `enrichir`, en SQL |
| `import_journal` | Source, fichier, nombre de lignes et date de chaque import | Fin du pipeline |

Deux formules sont à connaître, toutes deux dans `charger.py` :

- **Marche** : distance à vol d'oiseau × 1,3, divisée par 75 mètres par minute, arrondie au supérieur. La jointure utilise `ST_DWithin` sur un rayon de 2 km.
- **Correspondance** : durée du premier tronçon + durée du second + 15 minutes. Elle n'est calculée que s'il n'existe pas de train direct, et plafonnée à 4 heures.

La colonne `geog` des tables `gare` et `poi` est générée par PostgreSQL à partir de la latitude et de la longitude. Un index GiST la rend rapide à interroger.

## Le trajet d'une question

Une question traverse dix étapes, toutes orchestrées par la fonction `repondre` de `app/ia/assistant.py`. C'est le fichier à lire en premier.

| Étape | Où dans le code | Ce qui se passe |
| --- | --- | --- |
| 1. Envoi | `web/lib/api.ts`, puis `main.py` | L'interface envoie la question, les critères du message précédent et la gare sélectionnée sur la carte |
| 2. Extraction | `_extraire` dans `assistant.py` | Appel à `extraction_llm.extraire` si un LLM est configuré ; en cas d'erreur ou sans LLM, `extraction_regles.extraire` |
| 3. Validation | `Criteres` dans `criteres.py` | Tout thème inconnu, toute durée absurde sont écartés, que les critères viennent du LLM ou des règles |
| 4. Mémoire | `fusionner` dans `criteres.py` | Ce que dit le nouveau message remplace l'ancien, le reste est conservé |
| 5. Départ | `resoudre_gare` dans `metier/gares.py` | Le nom de ville est cherché dans la table des gares ; à défaut, la gare sélectionnée, puis Grenoble avec un avertissement |
| 6. Recherche | `rechercher` dans `metier/destinations.py` | Deux requêtes SQL : les gares accessibles dans le temps donné, puis leurs lieux du bon thème à distance de marche |
| 7. Classement | `calculer` dans `metier/scoring.py` | Un score par destination, tri, cinq premières conservées |
| 8. Gabarits | `redaction.py` | Une phrase de justification par destination, construite à partir des données |
| 9. Rédaction LLM | `rediger_avec_llm` dans `redaction.py` | Si le LLM répond correctement, ses phrases remplacent les gabarits |
| 10. Réponse | `repondre` | Un objet JSON : critères compris, critères appliqués, destinations, détail du score, avertissements, moteur utilisé, mesures |

Trois cas particuliers sont gérés dans `repondre` :

- **« Que faire autour de cette gare ? »** : si une gare est sélectionnée et que la question contient « autour », « ici » ou « cette gare », la gare devient la destination et non le départ.
- **Aucun résultat** : `_contrainte_bloquante` cherche de combien il faudrait assouplir la marche ou le trajet, et le message le dit.
- **Aucun thème demandé** : la recherche se limite aux activités (`THEMES_ACTIVITE`), sans hébergements ni événements.

### L'extraction par règles

`extraction_regles.py` fonctionne sans aucun appel externe. Elle sert de repli et de point de comparaison.

- **Durées** : des expressions régulières reconnaissent « 1h30 », « deux heures », « une demi-heure », « 20 min ». Une durée devient un temps de marche si « marche » ou « à pied » se trouve juste à côté ; sinon c'est un temps de trajet.
- **Départ** : un nom de gare connu précédé de « de », « depuis » ou « au départ de ».
- **Thèmes, public, difficulté** : des listes de mots, sans accents.

## Le classement

Chaque destination reçoit un score sur 100, somme de cinq composantes pondérées. Tout est dans `metier/scoring.py`, une soixantaine de lignes sans base ni LLM.

Exemple calculé à la main : une gare à 30 minutes en direct pour un maximum de 2 heures, 5 trains par jour, deux lieux correspondants (une randonnée à 5 minutes à pied, un site naturel à 10 minutes), pour une demande « randonnée et nature » avec 20 minutes de marche au plus.

| Composante | Calcul | Valeur | Poids | Points |
| --- | --- | --- | --- | --- |
| Thèmes demandés couverts | 2 thèmes sur 2 | 1,00 | 35 % | 35 |
| Nombre de lieux | 2 lieux, plafond à 5 | 0,40 | 20 % | 8 |
| Temps de trajet | 1 − 30 / 120 | 0,75 | 20 % | 15 |
| Marche depuis la gare | 1 − 5 / 20, lieu le plus proche | 0,75 | 15 % | 11,25 |
| Fréquence des trains | 5 trains, plafond à 10 | 0,50 | 10 % | 5 |
| **Total** |  |  |  | **74** |

Chaque correspondance retire ensuite 10 points. Ce calcul exact est vérifié par le test `test_detail_du_calcul`.

Les poids sont un choix d'équipe, pas une vérité. Ils se règlent dans le dictionnaire `POIDS`, et l'interface affiche le détail sous chaque destination : c'est ce qui rend la recommandation explicable.

## Le LLM

Le LLM fait deux appels courts par question et ne voit jamais la base : il reçoit une phrase, puis une liste de résultats déjà choisis.

`llm.py` contient un seul client, compatible avec le format « chat completions » d'OpenAI. Ollama en local et la plupart des fournisseurs cloud l'acceptent, donc changer de modèle revient à changer trois variables : `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`. La température est à zéro et la réponse est demandée en JSON.

### Ce qui l'empêche d'inventer

| Garde-fou | Où dans le code |
| --- | --- |
| Le LLM ne fournit que des critères, jamais une destination | Consigne de `extraction_llm.py` |
| Un thème inconnu ou une durée absurde sont écartés | Validateurs de `Criteres` |
| La ville de départ doit exister dans la table des gares | `resoudre_gare` |
| Le LLM rédacteur ne reçoit que les destinations retenues | `rediger_avec_llm` |
| Une justification portant sur une gare absente des résultats est jetée | Filtre sur `ids_connus` dans `rediger_avec_llm` |
| LLM en panne, trop lent ou réponse illisible : repli sur règles et gabarits | `ErreurLLM`, attrapée dans `assistant.py` |

### Ce qu'on a mesuré

Mesures du 5 octobre, sur un portable sans carte graphique, avec les 12 requêtes de la série « nouvelles ».

|  | Règles seules | llama3.2:3b en local |
| --- | --- | --- |
| Critères conformes | 7 sur 12 | 3 sur 12 |
| Contraintes respectées dans les résultats | 12 sur 12 | 12 sur 12 |
| Temps médian par question | environ 40 ms | 92 secondes |
| Jetons par question | aucun | environ 1 800 en entrée, 250 en sortie |

Un modèle plus gros, Mistral 7B, dépassait le délai de 60 secondes sur la plupart des appels.

Lecture : sur cette machine, le petit modèle local est plus lent et moins précis que les règles. Il oublie des thèmes évidents (« musée »), se trompe sur des durées et en invente parfois. En revanche les résultats affichés respectent toujours les contraintes, ce qui montre que les garde-fous tiennent même quand le modèle se trompe.

La mesure d'un modèle cloud, avec le même script, reste à faire.

## L'interface

L'interface ne contient aucune logique métier : elle affiche ce que l'API renvoie. Tout l'état est dans un seul fichier, `web/app/page.tsx`.

| Fichier | Rôle |
| --- | --- |
| `app/page.tsx` | L'état partagé : la conversation (`echanges`), la gare sélectionnée (`gareActive`), ses lieux (`pois`), l'onglet ouvert |
| `components/Assistant.tsx` | Onglet Demander : saisie, critères compris, liste des destinations |
| `components/Itineraire.tsx` | Une destination, dessinée comme un plan de ligne, avec le détail du score |
| `components/Explorer.tsx` | Onglet Explorer : liste des gares, puis fiche d'une gare avec filtre par thème |
| `components/Carte.tsx` | La carte Leaflet : gares, départ, destinations numérotées, lieux, tracés, regroupement des points proches |
| `lib/api.ts` | Les quatre appels à l'API |
| `lib/types.ts` | La forme des données échangées |

Trois points techniques à savoir expliquer :

- **La carte est chargée uniquement dans le navigateur.** Leaflet a besoin de l'objet `window`, absent côté serveur. D'où l'import `dynamic(..., { ssr: false })` dans `page.tsx`.
- **La synchronisation va dans les deux sens.** Une réponse de l'assistant met à jour les marqueurs de la carte. Un clic sur une gare de la carte la place dans `gareActive`, qui part avec la question suivante sous le nom `gare_selectionnee`.
- **La mémoire de conversation est tenue par le navigateur.** Les critères de la dernière réponse sont renvoyés tels quels dans le champ `contexte`. Le serveur ne garde rien, ce qui respecte la consigne « pas d'historique persistant ».

### La carte : tracés et regroupement

Trois mécanismes à savoir expliquer :

- **Le tracé d'un trajet passe par les arrêts réels du train.** À l'ingestion, `_tracer` (dans `gtfs.py`) choisit pour chaque liaison le train qui circule le plus souvent, puis garde la position de tous ses arrêts entre la gare de montée et la gare de descente, y compris ceux situés hors de la région. Le résultat est rangé dans `liaison.trace`. À la recherche, `_ajouter_traces` (dans `destinations.py`) le joint aux destinations retenues ; avec une correspondance, il met les deux tronçons bout à bout, et la carte les dessine en tirets. Sans l'étape suivante, le trait reste droit entre deux arrêts.
- **Avec le tracé des lignes SNCF, le trajet suit les rails.** C'est une étape facultative de l'ingestion, dans `voies.py`, lancée par `python -m ingestion.voies` (ou l'option `--voies` du pipeline). Elle télécharge le fichier « formes des lignes du Réseau Ferré National » de SNCF Open Data. `lire_lignes_sncf` en fait un graphe : un nœud par point du tracé, une arête entre deux points voisins ; les lignes fermées ou déclassées sont écartées, et seules les lignes de la zone de nos gares sont gardées. Une ligne qui se branche sur une autre s'arrête près d'elle sans partager de point : `relier_les_extremites` raccorde donc chaque bout de ligne à la ligne voisine située à moins de 150 m. Pour chaque couple d'arrêts successifs d'un trajet, `troncon` accroche chaque arrêt au nœud le plus proche (400 m au plus), puis `chemin` cherche le plus court chemin entre les deux avec l'algorithme A*. `simplifier` allège ensuite la ligne (algorithme de Douglas-Peucker, à 15 m près). Si aucun chemin raisonnable n'existe, le segment reste droit. Le même module sait lire les voies d'OpenStreetMap via Overpass (`--osm`), gardé en secours : ses serveurs publics ne répondaient pas pendant le projet.
- **Les points qui se chevauchent sont regroupés.** La fonction `regrouper` convertit chaque point en pixels au zoom courant ; un point rejoint le premier groupe situé à moins de 24 pixels, sinon il en fonde un. Un groupe s'affiche comme une pastille portant le nombre de points ; un clic zoome dessus. Le calcul est refait à chaque changement de zoom, et à partir du zoom 17 plus rien n'est regroupé. Le départ, les destinations recommandées et la gare active ne sont jamais regroupés.

Le calque « Voies ferrées », à cocher en haut à droite de la carte, superpose les tuiles d'OpenRailwayMap. OpenRailwayMap est un rendu d'OpenStreetMap : ses tuiles sont des images, sur lesquelles on ne peut rien calculer. Nos tracés et ce calque viennent donc des mêmes données, et doivent se superposer.

Pourquoi un graphe et un calcul de chemin ? Le fichier donne la forme de chaque ligne, pas un itinéraire : pour tracer Grenoble–Chambéry il faut reconstruire le réseau et y chercher un chemin entre les deux gares. Le GTFS de la SNCF, à notre connaissance, ne contient pas de fichier `shapes.txt`, qui aurait donné cette géométrie (à vérifier avec `tar -tf donnees\brut\gtfs-sncf.zip`). Les arrêts intermédiaires guident ce calcul : le chemin est cherché d'un arrêt au suivant, ce qui évite de prendre une autre ligne que celle du train.

### Les services en gare

La fiche d'une gare et chaque destination recommandée affichent une rangée de pictogrammes : assistance PMR, équipements d'accessibilité, ascenseurs, vélo, cars, vente de billets, Wi-Fi, équipements proches.

- **La liste est fermée** : `app/services.py` donne le code et le libellé de chaque service, dans l'ordre d'affichage.
- **Six fichiers SNCF Open Data**, lus par `ingestion/services.py`, un lecteur de dix lignes par fichier. Le rattachement à nos gares dépend de ce que le fichier fournit : le code UIC (assistance PMR, équipements d'accessibilité, points de vente), le code à trois lettres ou le nom (vélo, Wi-Fi), ou seulement une position (ascenseurs, rattachés à la gare située à moins de 400 m).
- **Les cars** viennent du GTFS : les gares où s'arrête une ligne de type 3.
- **Parking, taxis, arrêt de bus, borne de recharge** viennent des points DATAtourisme sans thème touristique situés à moins de 400 m de la gare. Le calcul est une requête SQL dans `charger.enrichir`.
- **Stockage** : table `gare_service`, une ligne par gare et par service, avec la précision affichée et la source.
- **API** : `GET /gares/{id}/services`. Les destinations de `/destinations` et de `/recherche` portent aussi les services de leur gare.
- **Interface** : `components/Pastilles.tsx` dessine les pictogrammes à partir de `lib/pictogrammes.ts` (tracés du jeu d'icônes libre Lucide). Chaque pastille porte son libellé pour les lecteurs d'écran et au survol.

Limites : ces fichiers ne couvrent pas toutes les gares, les équipements DATAtourisme sont incomplets, et aucune source chargée ne décrit les tramways ni les parkings gérés par la SNCF.

## Tests et évaluation

Deux outils distincts : les tests vérifient que le code fait ce qu'il doit, l'évaluation mesure la qualité de la compréhension.

### Les tests

69 tests, lancés par `docker compose run --rm api pytest`. 53 tournent sans base ni réseau ; 16 rejouent la chaîne complète sur le jeu d'essai et demandent une base dédiée (voir le README).

| Fichier | Ce qu'il vérifie |
| --- | --- |
| `test_ingestion.py` | Nettoyage des trois sources, rattachement des arrêts, durées, passage après minuit, thèmes |
| `test_scoring.py` | La formule de classement, dont le calcul détaillé plus haut |
| `test_extraction_regles.py` | Les requêtes du sujet, les durées de trajet et de marche, la ville de départ |
| `test_criteres.py` | La validation et la mémoire de conversation |
| `test_redaction.py` | Les gabarits, et le rejet d'une gare inventée par le LLM |
| `test_api.py` | La chaîne complète, y compris un LLM simulé qui invente et un LLM en panne |

Les tests ont été éprouvés : en inversant volontairement un filtre ou en retirant un garde-fou, ils échouent bien.

### L'évaluation

`python -m evaluation.evaluer` rejoue les requêtes de `evaluation/requetes.json` et affiche, pour chacune :

- si les critères extraits sont ceux attendus, avec le détail des écarts ;
- si chaque résultat respecte les contraintes appliquées ;
- qui a réellement répondu, le LLM ou le repli ;
- le temps et les jetons consommés.

Les requêtes sont réparties en deux séries. La série « sujet » reprend les 9 exemples de l'énoncé ; les règles y font 9 sur 9, mais elles ont été écrites à partir de ces phrases. La série « nouvelles » contient 12 formulations inédites : c'est elle qui mesure quelque chose.

| Commande | Usage |
| --- | --- |
| `... evaluer` | Avec le LLM configuré |
| `... evaluer --sans-llm` | Règles seules, point de comparaison |
| `... evaluer --serie nouvelles` | Une seule série, utile quand le LLM est lent |
| `... evaluer --csv resultats.csv` | Détail par requête dans un fichier |

## Modifier le code

La plupart des changements touchent un seul fichier. Le code du backend est monté dans le conteneur : une modification est prise en compte sans reconstruire l'image.

| Pour... | Modifier... | Puis... |
| --- | --- | --- |
| Donner un thème à un type DATAtourisme | `MOTS_CLES` ou `TYPES_EXACTS` dans `app/themes.py` | Relancer le pipeline |
| Écarter un type sans intérêt touristique | `TYPES_SANS_THEME` dans `app/themes.py` | Relancer le pipeline |
| Changer un poids du classement | `POIDS` dans `app/metier/scoring.py` | Adapter `test_scoring.py` |
| Changer le rayon de 2 km, la vitesse de marche, la marge de correspondance | `app/config.py` | Relancer le pipeline : ces valeurs sont calculées à l'ingestion |
| Réduire le périmètre à quelques départements | `DEPARTEMENTS` dans `app/config.py` | Relancer le pipeline |
| Inclure les cars en plus des trains | `TYPES_ROUTE_GTFS` dans `app/config.py` | Relancer le pipeline |
| Changer de modèle ou de fournisseur | Les variables `LLM_...` du fichier `.env` | `docker compose up -d api` |
| Améliorer la consigne d'extraction | `CONSIGNE` dans `app/ia/extraction_llm.py` | Relancer l'évaluation |
| Ajouter une requête de test | `evaluation/requetes.json` | Relancer l'évaluation |
| Ajouter un point d'accès | Une fonction dans `app/metier/`, puis une route dans `app/main.py` | Vérifier sur `/docs` |
| Ajouter une source de données | Un module dans `ingestion/`, une table dans `db/schema.sql`, un appel dans `executer` | Relancer le pipeline |

Relancer le pipeline : `docker compose run --rm api python -m ingestion.pipeline`. Sans l'option `--telecharger`, il réutilise les fichiers déjà présents et prend une trentaine de secondes.

## Questions probables en soutenance

Chaque réponse tient en deux phrases et renvoie à un endroit précis du code.

| Question | Réponse courte |
| --- | --- |
| Pourquoi ne pas demander directement des destinations au LLM ? | Il en inventerait. Chez nous il ne fournit que des critères, puis rédige à partir de résultats déjà choisis par `metier/destinations.py`. |
| Comment calculez-vous un temps de trajet ? | C'est la durée médiane des trains directs entre deux gares, tirée des horaires GTFS (`calculer_liaisons`). Avec une correspondance, c'est une estimation : les deux tronçons plus 15 minutes. |
| Le trait sur la carte, c'est la voie ferrée ? | Oui quand le tracé des lignes SNCF est chargé (`python -m ingestion.voies`) : entre deux arrêts successifs du train, on cherche le plus court chemin dans le graphe du réseau ferré national. C'est un chemin plausible, pas la voie exacte empruntée : les horaires ne disent pas quelle voie prend le train. Sans ces données, ou sans chemin trouvé, le segment est droit. |
| Comment savez-vous qu'un lieu est à 20 minutes à pied ? | Distance à vol d'oiseau majorée de 30 %, à 4,5 km/h. C'est une estimation ; un vrai itinéraire piéton sur OpenStreetMap serait l'étape suivante. |
| Comment croisez-vous les sources ? | Gares et horaires par code UIC, sinon par proximité à moins de 300 m. Gares et lieux par distance, avec `ST_DWithin` de PostGIS. |
| Que se passe-t-il si le LLM tombe en panne ? | L'application bascule sur des règles et des gabarits, et l'indique. On peut le montrer en vidant `LLM_BASE_URL`. |
| Comment limitez-vous les hallucinations ? | Six garde-fous, listés dans la section LLM. Le principal : toute gare citée doit exister dans les résultats, sinon la phrase est jetée. |
| Le LLM apporte-t-il vraiment quelque chose ? | Mesuré honnêtement : un petit modèle local fait 3 sur 12 contre 7 sur 12 pour les règles, en 92 secondes. La réponse dépend du modèle ; le cloud reste à mesurer. |
| Comment classez-vous les résultats ? | Par une formule à cinq composantes, dans `scoring.py`, affichée à l'utilisateur sous chaque destination. |
| Que fait l'application quand elle ne sait pas ? | Elle le dit : gare introuvable, critère non vérifiable comme la difficulté, ou aucun résultat avec la contrainte à assouplir. |
| Pourquoi PostGIS ? | Pour faire la jointure spatiale entre 329 gares et 58 000 lieux en une requête indexée, dans le même moteur que les jointures classiques. |
| Pourquoi 15 % des lieux n'ont-ils pas de thème ? | Ce sont des commerces et des services (pharmacies, taxis, parkings). Ils sont écartés volontairement, et la liste est dans `TYPES_SANS_THEME`. |
| Vos données sont-elles à jour ? | Les horaires couvrent du 2 octobre 2026 au 31 mars 2027 ; DATAtourisme est mis à jour chaque jour. Une commande les retélécharge. |
| Qu'avez-vous écrit vous-mêmes ? | Le socle a été produit avec un assistant de développement, comme le sujet l'autorise. Nous l'avons relu, lancé sur les données réelles, ajusté (thèmes, requêtes de test) et mesuré. |

## Limites connues

Mieux vaut les annoncer que se les faire signaler.

- **Correspondances** : une seule au maximum, et sa durée ignore les horaires réels.
- **Marche** : une estimation à vol d'oiseau, pas un itinéraire piéton.
- **Difficulté des randonnées** : absente de l'export CSV de DATAtourisme. Le critère est compris, signalé, et non appliqué.
- **Événements** : leurs dates ne sont pas contrôlées. Ils sont exclus des recherches sans thème et signalés quand ils sont demandés.
- **Activités encadrées** : la position enregistrée est celle du prestataire, pas forcément du lieu de l'activité.
- **Thèmes** : attribués par mots-clés. Une dégustation de vin ressort aussi en « sport et loisirs ».
- **Texte du LLM** : il n'est pas contrôlé mot à mot. Un modèle pourrait glisser un fait faux dans une phrase portant sur une vraie gare.
- **Consigne d'extraction** : elle donne au modèle le nom des thèmes sans les définir, ce qui explique une partie de ses erreurs.
- **Règles d'extraction** : écrites à partir des phrases du sujet. Elles échouent sur « trois quarts d'heure » ou « une heure trente ».
- **Carte** : le tracé le long des voies est un plus court chemin entre arrêts, pas la voie réellement empruntée. Il n'a été vérifié que sur un réseau inventé : sur les vraies données, lire le bilan « tracés le long des voies » du pipeline et contrôler quelques trajets avec le calque « Voies ferrées ».
- **Interface** : aucun test automatique, elle se vérifie à la main.
