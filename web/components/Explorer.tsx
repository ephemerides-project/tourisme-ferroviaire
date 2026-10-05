"use client";

// Onglet « Explorer » : parcourir les gares, puis les points d'intérêt autour d'une gare.

import { useMemo, useState } from "react";

import { dureeLisible, libelleTheme } from "@/lib/format";
import type { Gare, Poi } from "@/lib/types";

type Props = {
  gares: Gare[];
  gareActive: Gare | null;
  pois: Poi[];
  surGare: (gare: Gare) => void;
  surFermer: () => void;
  surPartirDIci: () => void;
};

const sansAccents = (texte: string) =>
  texte
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

export default function Explorer({ gares, gareActive, pois, surGare, surFermer, surPartirDIci }: Props) {
  const [filtre, setFiltre] = useState("");
  const [theme, setTheme] = useState<string | null>(null);

  const garesFiltrees = useMemo(
    () => gares.filter((g) => sansAccents(g.nom).includes(sansAccents(filtre.trim()))),
    [gares, filtre],
  );
  const themesPresents = useMemo(() => Array.from(new Set(pois.flatMap((p) => p.themes))).sort(), [pois]);
  const poisFiltres = theme && themesPresents.includes(theme) ? pois.filter((p) => p.themes.includes(theme)) : pois;

  if (gareActive) {
    return (
      <div className="explorer">
        <button type="button" className="lien" onClick={surFermer}>
          Retour à la liste des gares
        </button>
        <h2 className="fiche__nom">{gareActive.nom}</h2>
        <p className="fiche__resume">
          {pois.length === 0
            ? "Aucun point d'intérêt à moins de 2 km de cette gare dans les données chargées."
            : `${pois.length} point${pois.length > 1 ? "s" : ""} d'intérêt à moins de 2 km de la gare.`}
        </p>
        <button type="button" className="bouton bouton--secondaire" onClick={surPartirDIci}>
          Chercher une sortie depuis cette gare
        </button>

        {themesPresents.length > 1 && (
          <div className="filtres" role="group" aria-label="Filtrer par thème">
            <button type="button" aria-pressed={theme === null} onClick={() => setTheme(null)}>
              Tout
            </button>
            {themesPresents.map((t) => (
              <button key={t} type="button" aria-pressed={theme === t} onClick={() => setTheme(t)}>
                {libelleTheme(t)}
              </button>
            ))}
          </div>
        )}

        <ul className="lieux">
          {poisFiltres.map((poi) => (
            <li key={poi.id}>
              <span className="lieux__minutes">{dureeLisible(poi.marche_min)} à pied</span>
              <span className="lieux__nom">{poi.nom}</span>
              <span className="lieux__themes">
                {[...poi.themes.map(libelleTheme), poi.commune].filter(Boolean).join(", ")}
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="explorer">
      <label htmlFor="filtre-gare">Chercher une gare</label>
      <input
        id="filtre-gare"
        type="search"
        value={filtre}
        onChange={(e) => setFiltre(e.target.value)}
        placeholder="Nom de la gare ou de la ville"
      />
      <p className="explorer__compte">
        {garesFiltrees.length} gare{garesFiltrees.length > 1 ? "s" : ""}. Cliquez sur une gare, ici ou sur la carte.
      </p>
      <ul className="gares">
        {garesFiltrees.map((gare) => (
          <li key={gare.id}>
            <button type="button" onClick={() => surGare(gare)}>
              <span className="gares__nom">{gare.nom}</span>
              <span className="gares__compte">
                {gare.nb_poi ? `${gare.nb_poi} lieu${gare.nb_poi > 1 ? "x" : ""}` : "aucun lieu"}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
