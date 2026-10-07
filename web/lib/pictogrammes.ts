// Pictogrammes des services de gare et des thèmes d'activité.
// Tracés repris du jeu d'icônes libre Lucide (https://lucide.dev, licence ISC,
// © Lucide Icons and Contributors) : chaque icône est une liste de formes SVG [balise, attributs],
// dessinées au trait dans une grille de 24 x 24.

export type Forme = [string, Record<string, string>];

export const PICTOGRAMMES: Record<string, Forme[]> = {
  pmr: [["circle", {"cx": "16", "cy": "4", "r": "1"}], ["path", {"d": "m18 19 1-7-6 1"}], ["path", {"d": "m5 8 3-3 5.5 3-2.36 3.5"}], ["path", {"d": "M4.24 14.5a5 5 0 0 0 6.88 6"}], ["path", {"d": "M13.76 17.5a5 5 0 0 0-6.88-6"}]], // accessibility
  accessibilite: [["path", {"d": "M6 8.5a6.5 6.5 0 1 1 13 0c0 6-6 6-6 10a3.5 3.5 0 1 1-7 0"}], ["path", {"d": "M15 8.5a2.5 2.5 0 0 0-5 0v1a2 2 0 1 1 0 4"}]], // ear
  ascenseur: [["path", {"d": "m21 16-4 4-4-4"}], ["path", {"d": "M17 20V4"}], ["path", {"d": "m3 8 4-4 4 4"}], ["path", {"d": "M7 4v16"}]], // arrow-up-down
  velo: [["circle", {"cx": "18.5", "cy": "17.5", "r": "3.5"}], ["circle", {"cx": "5.5", "cy": "17.5", "r": "3.5"}], ["circle", {"cx": "15", "cy": "5", "r": "1"}], ["path", {"d": "M12 17.5V14l-3-3 4-3 2 3h2"}]], // bike
  car: [["path", {"d": "M8 6v6"}], ["path", {"d": "M15 6v6"}], ["path", {"d": "M2 12h19.6"}], ["path", {"d": "M18 18h3s.5-1.7.8-2.8c.1-.4.2-.8.2-1.2 0-.4-.1-.8-.2-1.2l-1.4-5C20.1 6.8 19.1 6 18 6H4a2 2 0 0 0-2 2v10h3"}], ["circle", {"cx": "7", "cy": "18", "r": "2"}], ["path", {"d": "M9 18h5"}], ["circle", {"cx": "16", "cy": "18", "r": "2"}]], // bus
  bus: [["path", {"d": "M4 6 2 7"}], ["path", {"d": "M10 6h4"}], ["path", {"d": "m22 7-2-1"}], ["rect", {"width": "16", "height": "16", "x": "4", "y": "3", "rx": "2"}], ["path", {"d": "M4 11h16"}], ["path", {"d": "M8 15h.01"}], ["path", {"d": "M16 15h.01"}], ["path", {"d": "M6 19v2"}], ["path", {"d": "M18 21v-2"}]], // bus-front
  parking: [["rect", {"width": "18", "height": "18", "x": "3", "y": "3", "rx": "2"}], ["path", {"d": "M9 17V7h4a3 3 0 0 1 0 6H9"}]], // square-parking
  taxi: [["path", {"d": "M10 2h4"}], ["path", {"d": "m21 8-2 2-1.5-3.7A2 2 0 0 0 15.646 5H8.4a2 2 0 0 0-1.903 1.257L5 10 3 8"}], ["path", {"d": "M7 14h.01"}], ["path", {"d": "M17 14h.01"}], ["rect", {"width": "18", "height": "8", "x": "3", "y": "10", "rx": "2"}], ["path", {"d": "M5 18v2"}], ["path", {"d": "M19 18v2"}]], // car-taxi-front
  covoiturage: [["path", {"d": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"}], ["path", {"d": "M16 3.128a4 4 0 0 1 0 7.744"}], ["path", {"d": "M22 21v-2a4 4 0 0 0-3-3.87"}], ["circle", {"cx": "9", "cy": "7", "r": "4"}]], // users
  recharge: [["path", {"d": "M6.3 20.3a2.4 2.4 0 0 0 3.4 0L12 18l-6-6-2.3 2.3a2.4 2.4 0 0 0 0 3.4Z"}], ["path", {"d": "m2 22 3-3"}], ["path", {"d": "M7.5 13.5 10 11"}], ["path", {"d": "M10.5 16.5 13 14"}], ["path", {"d": "m18 3-4 4h6l-4 4"}]], // plug-zap
  billets: [["path", {"d": "M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"}], ["path", {"d": "M13 5v2"}], ["path", {"d": "M13 17v2"}], ["path", {"d": "M13 11v2"}]], // ticket
  wifi: [["path", {"d": "M12 20h.01"}], ["path", {"d": "M2 8.82a15 15 0 0 1 20 0"}], ["path", {"d": "M5 12.859a10 10 0 0 1 14 0"}], ["path", {"d": "M8.5 16.429a5 5 0 0 1 7 0"}]], // wifi
  toilettes: [["path", {"d": "M7 12h13a1 1 0 0 1 1 1 5 5 0 0 1-5 5h-.598a.5.5 0 0 0-.424.765l1.544 2.47a.5.5 0 0 1-.424.765H5.402a.5.5 0 0 1-.424-.765L7 18"}], ["path", {"d": "M8 18a5 5 0 0 1-5-5V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8"}]], // toilet
  eau: [["path", {"d": "M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"}]], // droplet
  nature: [["path", {"d": "M10 10v.2A3 3 0 0 1 8.9 16H5a3 3 0 0 1-1-5.8V10a3 3 0 0 1 6 0Z"}], ["path", {"d": "M7 16v6"}], ["path", {"d": "M13 19v3"}], ["path", {"d": "M12 19h8.3a1 1 0 0 0 .7-1.7L18 14h.3a1 1 0 0 0 .7-1.7L16 9h.2a1 1 0 0 0 .8-1.7L13 3l-1.4 1.5"}]], // trees
  randonnee: [["path", {"d": "M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z"}], ["path", {"d": "M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z"}], ["path", {"d": "M16 17h4"}], ["path", {"d": "M4 13h4"}]], // footprints
  montagne: [["path", {"d": "m8 3 4 8 5-5 5 15H2L8 3z"}], ["path", {"d": "M4.14 15.08c2.62-1.57 5.24-1.43 7.86.42 2.74 1.94 5.49 2 8.23.19"}]], // mountain-snow
  patrimoine: [["path", {"d": "M10 5V3"}], ["path", {"d": "M14 5V3"}], ["path", {"d": "M15 21v-3a3 3 0 0 0-6 0v3"}], ["path", {"d": "M18 3v8"}], ["path", {"d": "M18 5H6"}], ["path", {"d": "M22 11H2"}], ["path", {"d": "M22 9v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9"}], ["path", {"d": "M6 3v8"}]], // castle
  culture: [["path", {"d": "M10 18v-7"}], ["path", {"d": "M11.119 2.205a2 2 0 0 1 1.762 0l7.84 3.846A.5.5 0 0 1 20.5 7h-17a.5.5 0 0 1-.22-.949z"}], ["path", {"d": "M14 18v-7"}], ["path", {"d": "M18 18v-7"}], ["path", {"d": "M3 22h18"}], ["path", {"d": "M6 18v-7"}]], // landmark
  famille: [["circle", {"cx": "12", "cy": "12", "r": "2"}], ["path", {"d": "M12 2v4"}], ["path", {"d": "m6.8 15-3.5 2"}], ["path", {"d": "m20.7 7-3.5 2"}], ["path", {"d": "M6.8 9 3.3 7"}], ["path", {"d": "m20.7 17-3.5-2"}], ["path", {"d": "m9 22 3-8 3 8"}], ["path", {"d": "M8 22h8"}], ["path", {"d": "M18 18.7a9 9 0 1 0-12 0"}]], // ferris-wheel
  sport_loisirs: [["path", {"d": "M11 7a16 16 20 0 1 10.98 4.362"}], ["path", {"d": "M12 12a13 13 0 0 1-8.66 5"}], ["path", {"d": "M16.83 13.634a16 16 0 0 1-9.267 7.328"}], ["path", {"d": "M20.66 17A13 13 0 0 0 12 12a13 13 0 0 1 0-10"}], ["path", {"d": "M8.17 15.366a16 16 0 0 1-1.713-11.69"}], ["circle", {"cx": "12", "cy": "12", "r": "10"}]], // volleyball
  gastronomie: [["path", {"d": "M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"}], ["path", {"d": "M7 2v20"}], ["path", {"d": "M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"}]], // utensils
  hebergement: [["path", {"d": "M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8"}], ["path", {"d": "M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4"}], ["path", {"d": "M12 4v6"}], ["path", {"d": "M2 18h20"}]], // bed-double
  evenement: [["path", {"d": "M8 2v3"}], ["path", {"d": "M16 2v3"}], ["rect", {"x": "3", "y": "3", "width": "18", "height": "18", "rx": "2"}], ["path", {"d": "M3 9h18"}], ["path", {"d": "M8 13h.01"}], ["path", {"d": "M12 13h.01"}], ["path", {"d": "M16 13h.01"}], ["path", {"d": "M8 17h.01"}], ["path", {"d": "M12 17h.01"}], ["path", {"d": "M16 17h.01"}]], // calendar-days
};
