import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "EdgarPack Observatory",
  description: "Filing diffs, timelines, and search over local EdgarPack packs.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
