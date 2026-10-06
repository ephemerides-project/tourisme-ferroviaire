// Formes des données échangées avec l'API (voir backend/app/main.py).

export type Gare = {
  id: string;
  nom: string;
  lat: number;
  lon: number;
  departement?: string | null;
  desservie?: boolean;
  nb_poi?: number;
};

export type Poi = {
  id: string;
  nom: string;
  themes: string[];
  lat: number;
  lon: number;
  commune: string | null;
  description?: string | null;
  distance_m: number;
  marche_min: number;
};

export type Criteres = {
  origine: string | null;
  duree_max_min: number | null;
  marche_max_min: number | null;
  themes: string[];
  public: "famille" | null;
  difficulte: "facile" | "moyen" | "difficile" | null;
};

export type Trajet = {
  duree_min: number;
  correspondances: number;
  via: string | null;
  trajets_jour: number;
  duree_estimee: boolean;
  trace?: [number, number][] | null; // points [lat, lon] du trajet, par les arrêts du train
};

export type DetailScore = {
  total: number;
  composantes: { themes: number; offre: number; trajet: number; marche: number; frequence: number };
  penalite_correspondance: number;
};

export type Destination = {
  gare: Gare;
  trajet: Trajet | null; // null en mode « autour de la gare »
  score: number | null;
  detail_score: DetailScore | null;
  nb_pois: number;
  pois: Poi[];
  justification: string;
};

export type Reponse = {
  question: string;
  criteres: Criteres;
  criteres_appliques: {
    themes: string[];
    duree_max_min: number;
    marche_max_min: number;
    valeurs_par_defaut: string[];
  };
  mode: "destinations" | "autour";
  origine: Gare | null;
  destinations: Destination[];
  introduction: string;
  avertissements: string[];
  moteur: { extraction: "llm" | "regles"; redaction: "llm" | "gabarit" };
};

export type Theme = { id: string; libelle: string };
