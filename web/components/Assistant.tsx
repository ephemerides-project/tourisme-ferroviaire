"use client";

// Onglet « Demander » : question en langage naturel, critères compris, destinations classées.

import { useState } from "react";

import { dureeLisible, libelleTheme } from "@/lib/format";
import type { Destination, Gare, Reponse } from "@/lib/types";

import Itineraire from "./Itineraire";

const EXEMPLES = [
  "Une sortie nature à moins de 1h30 de Grenoble, avec une randonnée à moins de 20 minutes de marche de la gare",
  "Une journée à la montagne à moins de 2 heures de Grenoble avec des enfants",
  "Un musée ou du patrimoine à une heure de Chambéry",
];

type Props = {
  echanges: Reponse[];
  enCours: boolean;
  gareActive: Gare | null;
  surQuestion: (question: string) => void;
  surRecommencer: () => void;
  surDestination: (destination: Destination) => void;
  surRetirerGare: () => void;
};

/** Ce que l'application a compris de la demande, pour que l'utilisateur puisse le vérifier. */
function CriteresCompris({ reponse }: { reponse: Reponse }) {
  const { criteres_appliques: appliques, origine, mode } = reponse;
  const parDefaut = (champ: string) => (appliques.valeurs_par_defaut.includes(champ) ? " (par défaut)" : "");
  return (
    <ul className="criteres" aria-label="Critères pris en compte">
      {origine && (
        <li className="criteres__depart">
          {mode === "autour" ? "Autour de" : "Départ"} : {origine.nom}
          {parDefaut("origine")}
        </li>
      )}
      {mode === "destinations" && (
        <li>
          Trajet : {dureeLisible(appliques.duree_max_min)} au plus{parDefaut("duree_max_min")}
        </li>
      )}
      <li>
        Marche : {dureeLisible(appliques.marche_max_min)} au plus{parDefaut("marche_max_min")}
      </li>
      {appliques.themes.map((theme) => (
        <li key={theme} className="criteres__theme">
          {libelleTheme(theme)}
        </li>
      ))}
    </ul>
  );
}

export default function Assistant(props: Props) {
  const { echanges, enCours, gareActive, surQuestion, surRecommencer, surDestination, surRetirerGare } = props;
  const [saisie, setSaisie] = useState("");
  const derniere = echanges[echanges.length - 1] ?? null;
  const precedentes = echanges.slice(0, -1);

  function envoyer(evenement: { preventDefault: () => void }) {
    evenement.preventDefault();
    const question = saisie.trim();
    if (question.length < 2 || enCours) return;
    surQuestion(question);
    setSaisie("");
  }

  return (
    <div className="assistant">
      <form className="saisie" onSubmit={envoyer}>
        <label htmlFor="question">{derniere ? "Précisez ou changez votre demande" : "Où voulez-vous aller en train ?"}</label>
        <textarea
          id="question"
          rows={3}
          value={saisie}
          onChange={(e) => setSaisie(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) envoyer(e);
          }}
          placeholder={
            derniere
              ? "Par exemple : et si je préfère quelque chose de culturel ?"
              : "Par exemple : une randonnée facile à moins d'une heure de Grenoble"
          }
        />
        {gareActive && (
          <p className="saisie__gare">
            Gare sélectionnée sur la carte : <strong>{gareActive.nom}</strong>
            <button type="button" className="lien" onClick={surRetirerGare}>
              Retirer
            </button>
          </p>
        )}
        <div className="saisie__actions">
          <button type="submit" className="bouton" disabled={enCours || saisie.trim().length < 2}>
            {enCours ? "Recherche en cours" : "Chercher"}
          </button>
          {derniere && (
            <button type="button" className="lien" onClick={surRecommencer}>
              Nouvelle recherche
            </button>
          )}
        </div>
      </form>

      {!derniere && (
        <section className="exemples">
          <h2>Quelques demandes pour essayer</h2>
          <ul>
            {(gareActive ? ["Que puis-je faire autour de cette gare avec des enfants ?", ...EXEMPLES.slice(0, 2)] : EXEMPLES).map(
              (exemple) => (
                <li key={exemple}>
                  <button type="button" onClick={() => surQuestion(exemple)} disabled={enCours}>
                    {exemple}
                  </button>
                </li>
              ),
            )}
          </ul>
        </section>
      )}

      {precedentes.length > 0 && (
        <ol className="fil" aria-label="Demandes précédentes">
          {precedentes.map((echange, i) => (
            <li key={i}>{echange.question}</li>
          ))}
        </ol>
      )}

      {derniere && (
        <section className="reponse" aria-live="polite">
          <p className="reponse__question">{derniere.question}</p>
          <CriteresCompris reponse={derniere} />
          <p className="reponse__intro">{derniere.introduction}</p>
          {derniere.avertissements.map((avertissement) => (
            <p key={avertissement} className="reponse__avertissement">
              {avertissement}
            </p>
          ))}
          <ol className="itineraires">
            {derniere.destinations.map((destination, i) => (
              <Itineraire
                key={destination.gare.id}
                rang={i + 1}
                destination={destination}
                origine={derniere.mode === "destinations" ? derniere.origine : null}
                active={gareActive?.id === destination.gare.id}
                surSelection={() => surDestination(destination)}
              />
            ))}
          </ol>
          <p className="reponse__moteur">
            {derniere.moteur.extraction === "llm" ? "Demande analysée par le modèle de langage." : "Demande analysée par règles, sans modèle de langage."}{" "}
            Les destinations viennent uniquement des données chargées.
          </p>
        </section>
      )}
    </div>
  );
}
