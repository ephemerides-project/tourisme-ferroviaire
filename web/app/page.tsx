"use client";

// Page unique : un panneau (Demander / Explorer) et la carte, synchronisés par l'état ci-dessous.

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import Assistant from "@/components/Assistant";
import Explorer from "@/components/Explorer";
import { demander, listerGares, poiDeLaGare } from "@/lib/api";
import type { Destination, Gare, Poi, Reponse } from "@/lib/types";

// Leaflet a besoin du navigateur : la carte n'est jamais rendue côté serveur.
const Carte = dynamic(() => import("@/components/Carte"), {
  ssr: false,
  loading: () => <p className="carte-attente">Chargement de la carte</p>,
});

type Onglet = "demander" | "explorer";

const message = (erreur: unknown) => (erreur instanceof Error ? erreur.message : String(erreur));

export default function Page() {
  const [onglet, setOnglet] = useState<Onglet>("demander");
  const [gares, setGares] = useState<Gare[]>([]);
  const [echanges, setEchanges] = useState<Reponse[]>([]); // la conversation en cours
  const [enCours, setEnCours] = useState(false);
  const [gareActive, setGareActive] = useState<Gare | null>(null); // gare sélectionnée (carte ou liste)
  const [pois, setPois] = useState<Poi[]>([]); // points d'intérêt affichés pour la gare active
  const [erreur, setErreur] = useState<string | null>(null);
  const derniereGareDemandee = useRef<string | null>(null);

  const derniere = echanges[echanges.length - 1] ?? null;
  const resultats = derniere?.mode === "destinations" ? derniere.destinations : [];
  const surLaCarte = onglet === "demander"; // en mode Explorer, la carte ne montre pas les recommandations

  useEffect(() => {
    listerGares()
      .then(setGares)
      .catch((e) => setErreur(message(e)));
  }, []);

  /** Sélectionne une gare. Si ses points d'intérêt sont déjà connus (résultat de recherche), on les réutilise. */
  async function ouvrirGare(gare: Gare, poisConnus?: Poi[]) {
    derniereGareDemandee.current = gare.id;
    setGareActive(gare);
    setPois(poisConnus ?? []);
    if (poisConnus) return;
    try {
      const recus = await poiDeLaGare(gare.id);
      if (derniereGareDemandee.current === gare.id) setPois(recus); // ignore une réponse arrivée trop tard
    } catch (e) {
      setErreur(message(e));
    }
  }

  function fermerGare() {
    derniereGareDemandee.current = null;
    setGareActive(null);
    setPois([]);
  }

  /** Clic sur la carte : une gare recommandée montre les lieux qui répondent à la demande. */
  function surGareDeLaCarte(gare: Gare) {
    const recommandee = resultats.find((d) => d.gare.id === gare.id);
    void ouvrirGare(gare, onglet === "demander" ? recommandee?.pois : undefined);
  }

  function surDestination(destination: Destination) {
    if (gareActive?.id === destination.gare.id) fermerGare();
    else void ouvrirGare(destination.gare, destination.pois);
  }

  async function poser(question: string) {
    setEnCours(true);
    setErreur(null);
    try {
      const reponse = await demander(question, derniere?.criteres ?? null, gareActive?.id ?? null);
      setEchanges((precedents) => [...precedents, reponse]);
      const autour = reponse.mode === "autour" ? reponse.destinations[0] : undefined;
      if (autour) void ouvrirGare(autour.gare, autour.pois);
      else if (reponse.mode === "destinations") fermerGare();
    } catch (e) {
      setErreur(message(e));
    } finally {
      setEnCours(false);
    }
  }

  function recommencer() {
    setEchanges([]);
    fermerGare();
  }

  return (
    <main className="appli">
      <section className="panneau">
        <header className="entete">
          <h1>Sorties en train</h1>
          <p>Auvergne-Rhône-Alpes, sans voiture</p>
        </header>

        <nav className="onglets" aria-label="Mode de recherche">
          <button type="button" aria-pressed={onglet === "demander"} onClick={() => setOnglet("demander")}>
            Demander
          </button>
          <button type="button" aria-pressed={onglet === "explorer"} onClick={() => setOnglet("explorer")}>
            Explorer
          </button>
        </nav>

        {erreur && (
          <p className="erreur" role="alert">
            {erreur}
          </p>
        )}

        {onglet === "demander" ? (
          <Assistant
            echanges={echanges}
            enCours={enCours}
            gareActive={gareActive}
            surQuestion={poser}
            surRecommencer={recommencer}
            surDestination={surDestination}
            surRetirerGare={fermerGare}
          />
        ) : (
          <Explorer
            gares={gares}
            gareActive={gareActive}
            pois={pois}
            surGare={(gare) => void ouvrirGare(gare)}
            surFermer={fermerGare}
            surPartirDIci={() => setOnglet("demander")}
          />
        )}
      </section>

      <div className="carte-zone">
        <Carte
          gares={gares}
          origine={surLaCarte && derniere?.mode === "destinations" ? derniere.origine : null}
          destinations={surLaCarte ? resultats : []}
          gareActive={gareActive}
          pois={pois}
          surGare={surGareDeLaCarte}
        />
      </div>
    </main>
  );
}
