// Mise en forme partagée par les composants.

export const LIBELLES_THEMES: Record<string, string> = {
  nature: "Nature",
  randonnee: "Randonnée",
  montagne: "Montagne",
  patrimoine: "Patrimoine",
  culture: "Culture",
  famille: "Famille",
  sport_loisirs: "Sport et loisirs",
  gastronomie: "Gastronomie",
  hebergement: "Hébergement",
  evenement: "Événement",
};

export const libelleTheme = (theme: string) => LIBELLES_THEMES[theme] ?? theme;

/** 95 -> « 1 h 35 », 45 -> « 45 min ». */
export function dureeLisible(minutes: number): string {
  const heures = Math.floor(minutes / 60);
  const reste = minutes % 60;
  if (heures === 0) return `${reste} min`;
  return reste ? `${heures} h ${String(reste).padStart(2, "0")}` : `${heures} h`;
}

/** 1.71 -> « environ 2 trains par jour ». */
export function frequenceLisible(trajetsJour: number): string {
  if (trajetsJour < 1) return "moins d'un train par jour";
  const arrondi = Math.round(trajetsJour);
  return `environ ${arrondi} train${arrondi > 1 ? "s" : ""} par jour`;
}
