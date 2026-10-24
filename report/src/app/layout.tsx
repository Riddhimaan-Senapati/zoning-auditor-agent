import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

const SELF_IDENTIFICATION =
  "Independent prototype built at Hackachusetts 2026. Not a City of Boston service. Findings are unreviewed until confirmed by staff.";

export const metadata: Metadata = {
  title: "Boston Zoning Code Auditor",
  description: SELF_IDENTIFICATION,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header role="banner">
          <p>{SELF_IDENTIFICATION}</p>
        </header>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
