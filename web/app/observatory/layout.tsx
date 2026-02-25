import type { ReactNode } from "react";
import Link from "next/link";

export const metadata = {
  title: "Filing Observatory",
  description: "Cross-corpus SEC filing analysis",
};

export default function ObservatoryLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="shell-root observatory-shell">
      <header className="panel topbar">
        <div className="topbar-left">
          <h1 className="obs-topbar-title">Filing Observatory</h1>
          <span className="muted obs-topbar-subtitle">
            EdgarPack cross-corpus analysis
          </span>
        </div>
        <nav className="topbar-actions" aria-label="observatory navigation">
          <Link href="/observatory" className="secondary-btn">
            Companies
          </Link>
          <Link href="/observatory/search" className="secondary-btn">
            Search
          </Link>
        </nav>
      </header>
      <main id="observatory-main" className="main-content">
        {children}
      </main>
    </div>
  );
}
