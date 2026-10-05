"use client";

// Carte Leaflet. Chargée uniquement dans le navigateur (voir l'import dynamique dans app/page.tsx),
// car Leaflet a besoin de `window`.

import "leaflet/dist/leaflet.css";

import { useEffect } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";

import { dureeLisible, libelleTheme } from "@/lib/format";
import type { Destination, Gare, Poi } from "@/lib/types";

type Point = [number, number];

const CENTRE_REGION: Point = [45.45, 5.3];
const COULEURS = { encre: "#17324d", depart: "#ffcf33", resultat: "#c8102e", poi: "#1f7a5c", blanc: "#ffffff" };

type Props = {
  gares: Gare[];
  origine: Gare | null;
  destinations: Destination[];
  gareActive: Gare | null; // gare sur laquelle la carte est centrée
  pois: Poi[]; // points d'intérêt de la gare active
  surGare: (gare: Gare) => void;
};

/** Recadre la carte quand la liste de points à montrer change. */
function Cadrage({ points }: { points: Point[] }) {
  const carte = useMap();
  const cle = JSON.stringify(points);
  useEffect(() => {
    const aMontrer: Point[] = JSON.parse(cle);
    if (aMontrer.length === 0) return;
    const animer = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (aMontrer.length === 1) {
      carte.setView(aMontrer[0], 14, { animate: animer });
    } else {
      carte.fitBounds(aMontrer, { padding: [56, 56], maxZoom: 14, animate: animer });
    }
  }, [carte, cle]);
  return null;
}

export default function Carte({ gares, origine, destinations, gareActive, pois, surGare }: Props) {
  const idsResultats = new Set(destinations.map((d) => d.gare.id));

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
      <Cadrage points={aCadrer} />

      {/* Traits schématiques départ -> destination : ce ne sont pas les voies ferrées. */}
      {origine &&
        destinations
          .filter((d) => d.trajet)
          .map((d) => (
            <Polyline
              key={`trait-${d.gare.id}`}
              positions={[
                [origine.lat, origine.lon],
                [d.gare.lat, d.gare.lon],
              ]}
              pathOptions={{
                color: COULEURS.encre,
                weight: 2,
                opacity: 0.55,
                dashArray: d.trajet && d.trajet.correspondances > 0 ? "6 8" : undefined,
              }}
            />
          ))}

      {/* Toutes les gares */}
      {gares
        .filter((g) => !idsResultats.has(g.id) && g.id !== origine?.id)
        .map((g) => (
          <CircleMarker
            key={g.id}
            center={[g.lat, g.lon]}
            radius={g.id === gareActive?.id ? 8 : 5}
            pathOptions={{ color: COULEURS.blanc, weight: 2, fillColor: COULEURS.encre, fillOpacity: 1 }}
            eventHandlers={{ click: () => surGare(g) }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              {g.nom}
            </Tooltip>
          </CircleMarker>
        ))}

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
            <Tooltip permanent direction="center" className="carte-numero">
              {rang + 1}
            </Tooltip>
          </CircleMarker>
        ))}

      {/* Points d'intérêt de la gare active */}
      {pois.map((p) => (
        <CircleMarker
          key={p.id}
          center={[p.lat, p.lon]}
          radius={7}
          pathOptions={{ color: COULEURS.blanc, weight: 2, fillColor: COULEURS.poi, fillOpacity: 1 }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            <strong>{p.nom}</strong>
            <br />
            {dureeLisible(p.marche_min)} à pied de la gare
            {p.themes.length > 0 && (
              <>
                <br />
                {p.themes.map(libelleTheme).join(", ")}
              </>
            )}
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
