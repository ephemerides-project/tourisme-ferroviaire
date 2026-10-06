"use client";

// Carte Leaflet. Chargée uniquement dans le navigateur (voir l'import dynamique dans app/page.tsx),
// car Leaflet a besoin de `window`.

import "leaflet/dist/leaflet.css";

import type { Map as CarteLeaflet } from "leaflet";
import { useEffect, useRef, useState } from "react";
import { CircleMarker, LayersControl, MapContainer, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";

import { dureeLisible, libelleTheme } from "@/lib/format";
import type { Destination, Gare, Poi } from "@/lib/types";

type Point = [number, number];

const CENTRE_REGION: Point = [45.45, 5.3];
const COULEURS = { encre: "#17324d", depart: "#ffcf33", resultat: "#c8102e", poi: "#1f7a5c", blanc: "#ffffff" };

// Regroupement des points trop proches à l'écran.
const RAYON_GROUPE_PX = 24; // deux points à moins de 24 px l'un de l'autre sont regroupés
const ZOOM_SANS_GROUPE = 17; // à partir de ce zoom, tous les points sont affichés séparément
const NOMS_DANS_INFOBULLE = 6;

type Props = {
  gares: Gare[];
  origine: Gare | null;
  destinations: Destination[];
  gareActive: Gare | null; // gare sur laquelle la carte est centrée
  pois: Poi[]; // points d'intérêt de la gare active
  surGare: (gare: Gare) => void;
};

type Groupe<T> = { membres: T[]; lat: number; lon: number };

/**
 * Regroupe les points qui se chevaucheraient à l'écran.
 * Chaque point rejoint le premier groupe situé à moins de 24 px, sinon il en fonde un nouveau.
 * Les distances sont mesurées en pixels « monde » au zoom courant : les groupes ne changent pas
 * quand on déplace la carte, seulement quand on zoome.
 */
function regrouper<T extends { lat: number; lon: number }>(points: T[], carte: CarteLeaflet, zoom: number): Groupe<T>[] {
  if (zoom >= ZOOM_SANS_GROUPE) return points.map((p) => ({ membres: [p], lat: p.lat, lon: p.lon }));
  const groupes: { x: number; y: number; membres: T[] }[] = [];
  for (const point of points) {
    const pixel = carte.project([point.lat, point.lon], zoom);
    const voisin = groupes.find((g) => Math.hypot(g.x - pixel.x, g.y - pixel.y) <= RAYON_GROUPE_PX);
    if (voisin) voisin.membres.push(point);
    else groupes.push({ x: pixel.x, y: pixel.y, membres: [point] });
  }
  return groupes.map(({ membres }) => ({
    membres,
    lat: membres.reduce((somme, p) => somme + p.lat, 0) / membres.length,
    lon: membres.reduce((somme, p) => somme + p.lon, 0) / membres.length,
  }));
}

/** Recadre la carte quand la liste de points à montrer change. */
function Cadrage({ points }: { points: Point[] }) {
  const carte = useMap();
  const cle = JSON.stringify(points);

  // Leaflet ignore tout recadrage demandé pendant une animation de zoom :
  // on note donc si une animation est en cours, pour attendre sa fin.
  const zoomEnCours = useRef(false);
  useMapEvents({
    zoomanim: () => {
      zoomEnCours.current = true;
    },
    zoomend: () => {
      zoomEnCours.current = false;
    },
  });

  useEffect(() => {
    const aMontrer: Point[] = JSON.parse(cle);
    if (aMontrer.length === 0) return;
    const recadrer = () => {
      const animer = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (aMontrer.length === 1) {
        carte.setView(aMontrer[0], 14, { animate: animer });
      } else {
        carte.fitBounds(aMontrer, { padding: [56, 56], maxZoom: 15, animate: animer });
      }
    };
    if (!zoomEnCours.current) {
      recadrer();
      return;
    }
    carte.once("zoomend", recadrer);
    return () => {
      carte.off("zoomend", recadrer);
    };
  }, [carte, cle]);
  return null;
}

/**
 * Un nombre affiché en permanence au centre d'un marqueur.
 * C'est un marqueur invisible à part : Leaflet n'accepte qu'une infobulle par marqueur,
 * et celle du marqueur visible sert au survol.
 */
function Etiquette({ position, texte }: { position: Point; texte: string | number }) {
  return (
    <CircleMarker center={position} radius={0} interactive={false} pathOptions={{ opacity: 0, fillOpacity: 0 }}>
      <Tooltip permanent direction="center" className="carte-numero">
        {texte}
      </Tooltip>
    </CircleMarker>
  );
}

/** Les noms des premiers membres d'un groupe, pour son infobulle. */
function NomsDuGroupe({ noms }: { noms: string[] }) {
  const reste = noms.length - NOMS_DANS_INFOBULLE;
  return (
    <>
      {noms.slice(0, NOMS_DANS_INFOBULLE).map((nom, i) => (
        <span key={i}>
          {nom}
          <br />
        </span>
      ))}
      {reste > 0 ? `et ${reste} de plus : cliquez pour zoomer` : "Cliquez pour zoomer"}
    </>
  );
}

/** Tout ce qui est dessiné sur la carte. Composant séparé pour pouvoir lire le zoom courant. */
function Couches({ gares, origine, destinations, gareActive, pois, surGare }: Props) {
  const carte = useMap();
  const [zoom, setZoom] = useState(carte.getZoom());
  useMapEvents({ zoomend: () => setZoom(carte.getZoom()) });

  const zoomerSur = (membres: { lat: number; lon: number }[]) =>
    carte.fitBounds(
      membres.map((m): Point => [m.lat, m.lon]),
      { padding: [72, 72], maxZoom: ZOOM_SANS_GROUPE },
    );

  // Les gares mises en avant (départ, résultats, gare active) ne sont jamais regroupées.
  const idsEnAvant = new Set(destinations.map((d) => d.gare.id));
  if (origine) idsEnAvant.add(origine.id);
  if (gareActive) idsEnAvant.add(gareActive.id);
  const groupesDeGares = regrouper(
    gares.filter((g) => !idsEnAvant.has(g.id)),
    carte,
    zoom,
  );
  const groupesDePois = regrouper(pois, carte, zoom);
  const activeEstOrdinaire = gareActive && gareActive.id !== origine?.id && !destinations.some((d) => d.gare.id === gareActive.id);

  return (
    <>
      {/* Tracé des trajets : il passe par les arrêts réels du train, en ligne droite entre deux arrêts. */}
      {origine &&
        destinations
          .filter((d) => d.trajet)
          .map((d) => {
            const trace = d.trajet?.trace;
            const positions: Point[] =
              trace && trace.length >= 2
                ? trace
                : [
                    [origine.lat, origine.lon],
                    [d.gare.lat, d.gare.lon],
                  ];
            return (
              <Polyline
                key={`trait-${d.gare.id}`}
                positions={positions}
                pathOptions={{
                  color: COULEURS.encre,
                  weight: 3,
                  opacity: 0.7,
                  dashArray: d.trajet && d.trajet.correspondances > 0 ? "6 8" : undefined,
                }}
              />
            );
          })}

      {/* Gares : seules, ou regroupées quand elles se chevauchent */}
      {groupesDeGares.map((groupe) =>
        groupe.membres.length === 1 ? (
          <CircleMarker
            key={groupe.membres[0].id}
            center={[groupe.lat, groupe.lon]}
            radius={5}
            pathOptions={{ color: COULEURS.blanc, weight: 2, fillColor: COULEURS.encre, fillOpacity: 1 }}
            eventHandlers={{ click: () => surGare(groupe.membres[0]) }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              {groupe.membres[0].nom}
            </Tooltip>
          </CircleMarker>
        ) : (
          <CircleMarker
            key={`gares-${groupe.membres[0].id}-${groupe.membres.length}`}
            center={[groupe.lat, groupe.lon]}
            radius={groupe.membres.length < 10 ? 12 : 15}
            pathOptions={{ color: COULEURS.blanc, weight: 3, fillColor: COULEURS.encre, fillOpacity: 1 }}
            eventHandlers={{ click: () => zoomerSur(groupe.membres) }}
          >
            <Tooltip direction="top" offset={[0, -14]}>
              <strong>{groupe.membres.length} gares</strong>
              <br />
              <NomsDuGroupe noms={groupe.membres.map((g) => g.nom)} />
            </Tooltip>
          </CircleMarker>
        ),
      )}
      {groupesDeGares
        .filter((groupe) => groupe.membres.length > 1)
        .map((groupe) => (
          <Etiquette
            key={`compte-gares-${groupe.membres[0].id}-${groupe.membres.length}`}
            position={[groupe.lat, groupe.lon]}
            texte={groupe.membres.length}
          />
        ))}

      {/* Gare active, quand ce n'est ni le départ ni une destination recommandée */}
      {activeEstOrdinaire && gareActive && (
        <CircleMarker
          center={[gareActive.lat, gareActive.lon]}
          radius={9}
          pathOptions={{ color: COULEURS.blanc, weight: 3, fillColor: COULEURS.encre, fillOpacity: 1 }}
        >
          <Tooltip direction="top" offset={[0, -10]}>
            {gareActive.nom}
          </Tooltip>
        </CircleMarker>
      )}

      {/* Gare de départ */}
      {origine && (
        <CircleMarker
          center={[origine.lat, origine.lon]}
          radius={10}
          pathOptions={{ color: COULEURS.encre, weight: 3, fillColor: COULEURS.depart, fillOpacity: 1 }}
          eventHandlers={{ click: () => surGare(origine) }}
        >
          <Tooltip direction="top" offset={[0, -10]}>
            Départ : {origine.nom}
          </Tooltip>
        </CircleMarker>
      )}

      {/* Destinations recommandées, numérotées dans l'ordre du classement */}
      {destinations
        .filter((d) => d.gare.id !== origine?.id)
        .map((d, rang) => (
          <CircleMarker
            key={`resultat-${d.gare.id}`}
            center={[d.gare.lat, d.gare.lon]}
            radius={13}
            pathOptions={{ color: COULEURS.blanc, weight: 3, fillColor: COULEURS.resultat, fillOpacity: 1 }}
            eventHandlers={{ click: () => surGare(d.gare) }}
          >
            <Tooltip direction="top" offset={[0, -14]}>
              {d.gare.nom}
            </Tooltip>
          </CircleMarker>
        ))}
      {destinations
        .filter((d) => d.gare.id !== origine?.id)
        .map((d, rang) => (
          <Etiquette key={`numero-${d.gare.id}`} position={[d.gare.lat, d.gare.lon]} texte={rang + 1} />
        ))}

      {/* Points d'intérêt de la gare active : seuls, ou regroupés */}
      {groupesDePois.map((groupe) =>
        groupe.membres.length === 1 ? (
          <CircleMarker
            key={groupe.membres[0].id}
            center={[groupe.lat, groupe.lon]}
            radius={7}
            pathOptions={{ color: COULEURS.blanc, weight: 2, fillColor: COULEURS.poi, fillOpacity: 1 }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>{groupe.membres[0].nom}</strong>
              <br />
              {dureeLisible(groupe.membres[0].marche_min)} à pied de la gare
              {groupe.membres[0].themes.length > 0 && (
                <>
                  <br />
                  {groupe.membres[0].themes.map(libelleTheme).join(", ")}
                </>
              )}
            </Tooltip>
          </CircleMarker>
        ) : (
          <CircleMarker
            key={`pois-${groupe.membres[0].id}-${groupe.membres.length}`}
            center={[groupe.lat, groupe.lon]}
            radius={groupe.membres.length < 10 ? 12 : 15}
            pathOptions={{ color: COULEURS.blanc, weight: 3, fillColor: COULEURS.poi, fillOpacity: 1 }}
            eventHandlers={{ click: () => zoomerSur(groupe.membres) }}
          >
            <Tooltip direction="top" offset={[0, -14]}>
              <strong>{groupe.membres.length} lieux</strong>
              <br />
              <NomsDuGroupe noms={groupe.membres.map((p) => p.nom)} />
            </Tooltip>
          </CircleMarker>
        ),
      )}
      {groupesDePois
        .filter((groupe) => groupe.membres.length > 1)
        .map((groupe) => (
          <Etiquette
            key={`compte-pois-${groupe.membres[0].id}-${groupe.membres.length}`}
            position={[groupe.lat, groupe.lon]}
            texte={groupe.membres.length}
          />
        ))}
    </>
  );
}

export default function Carte(props: Props) {
  const { gares, origine, destinations, gareActive, pois } = props;

  // Ce que la carte doit montrer, par ordre de priorité.
  let aCadrer: Point[];
  if (gareActive) {
    aCadrer = [[gareActive.lat, gareActive.lon], ...pois.map((p): Point => [p.lat, p.lon])];
  } else if (destinations.length > 0) {
    aCadrer = destinations.map((d): Point => [d.gare.lat, d.gare.lon]);
    if (origine) aCadrer.push([origine.lat, origine.lon]);
  } else {
    aCadrer = gares.map((g): Point => [g.lat, g.lon]);
  }

  return (
    <MapContainer center={CENTRE_REGION} zoom={8} className="carte" scrollWheelZoom>
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; contributeurs <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />
      {/* Calque facultatif : le vrai réseau ferré, à cocher en haut à droite de la carte. */}
      <LayersControl position="topright">
        <LayersControl.Overlay name="Voies ferrées">
          <TileLayer
            url="https://tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png"
            maxZoom={19}
            opacity={0.8}
            attribution='Style : <a href="https://www.openrailwaymap.org/">OpenRailwayMap</a>, CC-BY-SA 2.0'
          />
        </LayersControl.Overlay>
      </LayersControl>
      <Cadrage points={aCadrer} />
      <Couches {...props} />
    </MapContainer>
  );
}
