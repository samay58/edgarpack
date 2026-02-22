import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Rogo China Lens",
  description: "Citation-backed workspace for Chinese primary source diligence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
