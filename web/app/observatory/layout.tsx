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
    <div className="shell-root">
      <header className="panel topbar">
        <div className="topbar-left">
          <h1 style={{ fontSize: "1.15rem" }}>Filing Observatory</h1>
          <span className="muted" style={{ fontSize: "0.85rem" }}>
            EdgarPack cross-corpus analysis
          </span>
        </div>
        <nav className="topbar-actions">
          <Link href="/observatory" className="secondary-btn">
            Companies
          </Link>
          <Link href="/observatory/search" className="secondary-btn">
            Search
          </Link>
        </nav>
      </header>
      {children}
    </div>
  );
}
