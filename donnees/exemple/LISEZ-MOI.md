# Jeu d'essai FICTIF

Ces fichiers reproduisent le **format** des vraies sources (export JSON SNCF, GTFS SNCF, CSV DATAtourisme)
avec un contenu inventé : 14 gares, une vingtaine de trains, 28 points d'intérêt « d'essai ».

Les noms de gares sont réels, mais les codes, les horaires et tous les points d'intérêt sont inventés.
Ce jeu sert à développer et à faire tourner les tests hors ligne.
**Il ne doit pas être utilisé pour une démonstration** : l'évaluation porte sur des données réelles.

    python -m ingestion.pipeline --exemple       # charge ce jeu d'essai
    python -m ingestion.pipeline --telecharger   # charge les vraies données
