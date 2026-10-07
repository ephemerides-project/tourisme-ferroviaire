// Rangée de pictogrammes : les services d'une gare, ou les activités possibles autour.

import { createElement } from "react";

import { PICTOGRAMMES } from "@/lib/pictogrammes";

export type Pastille = { code: string; libelle: string; detail?: string | null };

/** Dessine un pictogramme à partir de sa liste de formes SVG. */
export function Pictogramme({ code }: { code: string }) {
  const formes = PICTOGRAMMES[code];
  if (!formes) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {formes.map(([balise, attributs], i) => createElement(balise, { key: i, ...attributs }))}
    </svg>
  );
}

type Props = {
  titre: string; // « 4 services », « 3 activités »
  pastilles: Pastille[];
  genre: "services" | "activites"; // fixe la couleur
};

export default function Pastilles({ titre, pastilles, genre }: Props) {
  if (pastilles.length === 0) return null;
  return (
    <div className={`pastilles pastilles--${genre}`}>
      <span className="pastilles__titre">{titre}</span>
      <ul>
        {pastilles.map((pastille) => (
          // Le libellé est lu par les lecteurs d'écran et s'affiche au survol : l'icône seule ne suffit pas.
          <li key={pastille.code} title={[pastille.libelle, pastille.detail].filter(Boolean).join(" : ")}>
            <Pictogramme code={pastille.code} />
            <span className="lecteur-ecran">{pastille.libelle}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
