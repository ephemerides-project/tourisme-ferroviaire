// Une destination recommandée, dessinée comme un plan de ligne :
// gare de départ -> trajet en train -> gare d'arrivée -> points d'intérêt à pied.

import Pastilles from "@/components/Pastilles";
import { dureeLisible, frequenceLisible, libelleTheme } from "@/lib/format";
import type { Destination, Gare } from "@/lib/types";

const COMPOSANTES: { cle: keyof NonNullable<Destination["detail_score"]>["composantes"]; libelle: string; poids: number }[] = [
  { cle: "themes", libelle: "Thèmes demandés couverts", poids: 35 },
  { cle: "offre", libelle: "Nombre de lieux correspondants", poids: 20 },
  { cle: "trajet", libelle: "Trajet court", poids: 20 },
  { cle: "marche", libelle: "Proximité de la gare", poids: 15 },
  { cle: "frequence", libelle: "Fréquence des trains", poids: 10 },
];

type Props = {
  rang: number;
  destination: Destination;
  origine: Gare | null;
  active: boolean;
  surSelection: () => void;
};

export default function Itineraire({ rang, destination, origine, active, surSelection }: Props) {
  const { gare, trajet, pois, nb_pois, justification, detail_score } = destination;
  const autres = nb_pois - pois.length;

  return (
    <li className={`itin${active ? " itin--active" : ""}`}>
      <button type="button" className="itin__entete" onClick={surSelection} aria-pressed={active}>
        {trajet && <span className="itin__rang">{rang}</span>}
        <span className="itin__nom">{gare.nom}</span>
        {trajet && <span className="itin__duree">{dureeLisible(trajet.duree_min)}</span>}
      </button>

      {trajet && origine && (
        <ol className="trace trace--train">
          <li className="trace__arret trace__arret--depart">{origine.nom}</li>
          <li className="trace__troncon">
            {trajet.correspondances > 0
              ? `Correspondance à ${trajet.via}, durée estimée`
              : `Train direct, ${frequenceLisible(trajet.trajets_jour)}`}
          </li>
          <li className="trace__arret">{gare.nom}</li>
        </ol>
      )}

      {gare.services && <Pastilles genre="services" titre="À la gare" pastilles={gare.services} />}

      <ol className="trace trace--marche">
        {pois.map((poi) => (
          <li key={poi.id} className="trace__lieu">
            <span className="trace__minutes">{dureeLisible(poi.marche_min)} à pied</span>
            <span className="trace__nom">{poi.nom}</span>
            <span className="trace__themes">{poi.themes.map(libelleTheme).join(", ")}</span>
          </li>
        ))}
        {autres > 0 && (
          <li className="trace__lieu trace__lieu--reste">
            et {autres} autre{autres > 1 ? "s" : ""} lieu{autres > 1 ? "x" : ""} à voir sur la carte
          </li>
        )}
      </ol>

      <p className="itin__pourquoi">{justification}</p>

      {detail_score && (
        <details className="itin__score">
          <summary>Pertinence {detail_score.total} sur 100</summary>
          <dl>
            {COMPOSANTES.map(({ cle, libelle, poids }) => (
              <div key={cle} className="jauge">
                <dt>
                  {libelle} <span className="jauge__poids">{poids} %</span>
                </dt>
                <dd>
                  <span className="jauge__barre" style={{ width: `${Math.round(detail_score.composantes[cle] * 100)}%` }} />
                </dd>
              </div>
            ))}
          </dl>
          {detail_score.penalite_correspondance > 0 && (
            <p className="itin__penalite">Correspondance : {detail_score.penalite_correspondance} points retirés.</p>
          )}
        </details>
      )}
    </li>
  );
}
