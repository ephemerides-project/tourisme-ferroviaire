import "./globals.css";

import type { Metadata, Viewport } from "next";
import { Barlow, Barlow_Semi_Condensed } from "next/font/google";

const texte = Barlow({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--police-texte" });
const titres = Barlow_Semi_Condensed({ subsets: ["latin"], weight: ["600", "700"], variable: "--police-titres" });

export const metadata: Metadata = {
  title: "Sorties en train — Auvergne-Rhône-Alpes",
  description: "Trouver des destinations et des activités accessibles en train depuis une gare de la région.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${texte.variable} ${titres.variable}`}>
      <body>{children}</body>
    </html>
  );
}
