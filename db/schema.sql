-- Schéma de la base « tourisme ferroviaire ».
-- Rejouable sans risque : tout est en IF NOT EXISTS.
-- Appliqué automatiquement par `python -m ingestion.pipeline`.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Référentiel des gares de la région (source : SNCF Open Data).
CREATE TABLE IF NOT EXISTS gare (
    id           TEXT PRIMARY KEY,              -- code UIC principal (8 chiffres)
    nom          TEXT NOT NULL,
    trigramme    TEXT,
    code_insee   TEXT,
    departement  TEXT,
    segment_drg  TEXT,                          -- catégorie SNCF de la gare (A, B, C)
    lat          DOUBLE PRECISION NOT NULL,
    lon          DOUBLE PRECISION NOT NULL,
    desservie    BOOLEAN NOT NULL DEFAULT FALSE, -- vrai si au moins une liaison GTFS
    geog         geography(Point, 4326)
                 GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED
);
CREATE INDEX IF NOT EXISTS gare_geog_idx ON gare USING gist (geog);

-- Une gare peut porter plusieurs codes UIC : cette table sert au rapprochement avec le GTFS.
CREATE TABLE IF NOT EXISTS gare_uic (
    uic      TEXT PRIMARY KEY,
    gare_id  TEXT NOT NULL REFERENCES gare (id) ON DELETE CASCADE
);

-- Points d'intérêt touristiques (source : DATAtourisme).
CREATE TABLE IF NOT EXISTS poi (
    id            TEXT PRIMARY KEY,             -- URI DATAtourisme
    nom           TEXT NOT NULL,
    themes        TEXT[] NOT NULL DEFAULT '{}', -- thèmes internes (voir app/themes.py)
    types_source  TEXT[] NOT NULL DEFAULT '{}', -- types d'origine, conservés pour la traçabilité
    lat           DOUBLE PRECISION NOT NULL,
    lon           DOUBLE PRECISION NOT NULL,
    commune       TEXT,
    code_postal   TEXT,
    description   TEXT,
    source        TEXT NOT NULL,
    maj           DATE,
    geog          geography(Point, 4326)
                  GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED
);
CREATE INDEX IF NOT EXISTS poi_geog_idx ON poi USING gist (geog);
CREATE INDEX IF NOT EXISTS poi_themes_idx ON poi USING gin (themes);

-- Rapprochement gare <-> point d'intérêt, calculé une fois à l'ingestion.
-- marche_min est une ESTIMATION : distance à vol d'oiseau x facteur de détour / vitesse de marche.
CREATE TABLE IF NOT EXISTS gare_poi (
    gare_id     TEXT NOT NULL REFERENCES gare (id) ON DELETE CASCADE,
    poi_id      TEXT NOT NULL REFERENCES poi (id) ON DELETE CASCADE,
    distance_m  INTEGER NOT NULL,
    marche_min  INTEGER NOT NULL,
    PRIMARY KEY (gare_id, poi_id)
);
CREATE INDEX IF NOT EXISTS gare_poi_poi_idx ON gare_poi (poi_id);

-- Services et accès d'une gare : assistance PMR, vélo, cars, équipements proches (voir app/services.py).
CREATE TABLE IF NOT EXISTS gare_service (
    gare_id  TEXT NOT NULL REFERENCES gare (id) ON DELETE CASCADE,
    code     TEXT NOT NULL,     -- pmr, velo, car, bus, parking...
    detail   TEXT,              -- précision affichée : « 40 places sécurisées »
    source   TEXT NOT NULL,
    PRIMARY KEY (gare_id, code)
);

-- Liaisons directes entre deux gares, calculées à partir des horaires théoriques GTFS.
CREATE TABLE IF NOT EXISTS liaison (
    origine_id      TEXT NOT NULL REFERENCES gare (id) ON DELETE CASCADE,
    destination_id  TEXT NOT NULL REFERENCES gare (id) ON DELETE CASCADE,
    duree_min       INTEGER NOT NULL,   -- durée médiane des trajets directs, en minutes
    trajets_jour    REAL NOT NULL,      -- nombre moyen de trajets directs par jour
    trace           JSONB,              -- tracé [[lat, lon], ...] passant par les arrêts du train le plus fréquent
    PRIMARY KEY (origine_id, destination_id)
);
-- Pour les bases créées avant l'ajout du tracé.
ALTER TABLE liaison ADD COLUMN IF NOT EXISTS trace JSONB;

-- Accessibilité d'une gare depuis une autre : liaisons directes + trajets à une correspondance.
-- Pour une correspondance, la durée est une ESTIMATION (somme des deux tronçons + marge fixe),
-- elle ne tient pas compte des horaires réels de correspondance.
CREATE TABLE IF NOT EXISTS accessibilite (
    origine_id       TEXT NOT NULL REFERENCES gare (id) ON DELETE CASCADE,
    destination_id   TEXT NOT NULL REFERENCES gare (id) ON DELETE CASCADE,
    duree_min        INTEGER NOT NULL,
    correspondances  SMALLINT NOT NULL,
    via_id           TEXT REFERENCES gare (id) ON DELETE CASCADE,
    trajets_jour     REAL NOT NULL,
    PRIMARY KEY (origine_id, destination_id)
);
CREATE INDEX IF NOT EXISTS accessibilite_duree_idx ON accessibilite (origine_id, duree_min);

-- Journal des imports : permet de montrer quelles données sont réellement chargées.
CREATE TABLE IF NOT EXISTS import_journal (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    detail      TEXT,
    lignes      INTEGER NOT NULL,
    termine_le  TIMESTAMPTZ NOT NULL DEFAULT now()
);
