"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { CommandPalette, type CommandAction } from "@/components/china-lens/command-palette";

type AppShellProps = {
  companyId: string;
  companyLabel: string;
  children: ReactNode;
};

export function AppShell({ companyId, companyLabel, children }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const pendingShortcut = useRef<string>("");
  const shortcutTimeout = useRef<number | null>(null);

  const nav = useMemo(
    () => [
      { label: "Overview", href: `/${companyId}/overview` },
      { label: "Packs", href: `/${companyId}/packs` },
      { label: "Evidence", href: `/${companyId}/evidence` },
      { label: "Monitor", href: `/${companyId}/overview?tab=monitor`, disabled: true },
    ],
    [companyId],
  );

  const commands: CommandAction[] = [
    {
      id: "generate-pack",
      label: "Generate Pack",
      description: "Create a new citation-backed pack",
      href: `/${companyId}/packs`,
    },
    {
      id: "open-pack-builder",
      label: "Open Pack Builder",
      description: "Create or resume a citation-backed pack",
      href: `/${companyId}/packs`,
    },
    {
      id: "search-evidence",
      label: "Search evidence",
      description: "Open Evidence Explorer",
      href: `/${companyId}/evidence`,
    },
  ];

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
        return;
      }

      if (event.key.toLowerCase() === "g") {
        pendingShortcut.current = "g";
        if (shortcutTimeout.current) {
          window.clearTimeout(shortcutTimeout.current);
        }
        shortcutTimeout.current = window.setTimeout(() => {
          pendingShortcut.current = "";
        }, 700);
        return;
      }

      if (event.key.toLowerCase() === "e" && pendingShortcut.current === "g") {
        pendingShortcut.current = "";
        router.push(`/${companyId}/evidence`);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [companyId, router]);

  return (
    <div className="shell-root">
      <header className="topbar panel">
        <div className="topbar-left">
          <strong>{companyLabel}</strong>
          <span className="muted">China Lens Workspace</span>
        </div>
        <div className="topbar-actions">
          <button
            className="primary-btn"
            type="button"
            onClick={() => router.push(`/${companyId}/packs`)}
          >
            Generate Pack
          </button>
          <button className="secondary-btn" type="button" onClick={() => setPaletteOpen(true)}>
            Cmd+K
          </button>
        </div>
      </header>
      <div className="shell-body">
        <aside className="sidebar panel" aria-label="Primary navigation">
          <nav>
            <ul>
              {nav.map((item) => (
                <li key={item.href}>
                  {item.disabled ? (
                    <span className="nav-disabled">{item.label}</span>
                  ) : (
                    <Link
                      href={item.href}
                      className={pathname === item.href ? "nav-link active" : "nav-link"}
                    >
                      {item.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </nav>
        </aside>
        <main className="main-content">{children}</main>
      </div>
      <CommandPalette
        actions={commands}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={(href) => router.push(href)}
      />
    </div>
  );
}
