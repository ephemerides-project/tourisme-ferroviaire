// Appels à l'API. Toute la logique (recherche, classement, IA) est côté serveur.

import type { Criteres, Gare, Poi, Reponse, Theme } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function appeler<T>(chemin: string, options?: RequestInit): Promise<T> {
  let reponse: Response;
  try {
    reponse = await fetch(`${API}${chemin}`, options);
  } catch {
    throw new Error(`L'API ne répond pas à l'adresse ${API}. Vérifiez qu'elle est démarrée.`);
  }
  if (!reponse.ok) {
    const detail = await reponse.json().catch(() => null);
    throw new Error(typeof detail?.detail === "string" ? detail.detail : `Erreur ${reponse.status} renvoyée par l'API.`);
  }
  return reponse.json() as Promise<T>;
}

export const listerGares = () => appeler<Gare[]>("/gares");

export const listerThemes = () => appeler<Theme[]>("/themes");

export function poiDeLaGare(gareId: string, themes: string[] = []): Promise<Poi[]> {
  const parametres = new URLSearchParams();
  themes.forEach((theme) => parametres.append("theme", theme));
  const requete = parametres.toString();
  return appeler<Poi[]>(`/gares/${encodeURIComponent(gareId)}/poi${requete ? `?${requete}` : ""}`);
}

export function demander(question: string, contexte: Criteres | null, gareSelectionnee: string | null): Promise<Reponse> {
  return appeler<Reponse>("/recherche", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, contexte, gare_selectionnee: gareSelectionnee }),
  });
}
