"use client";

import { useEffect, useMemo, useState } from "react";

export type CommandAction = {
  id: string;
  label: string;
  description: string;
  href: string;
};

type CommandPaletteProps = {
  actions: CommandAction[];
  open: boolean;
  onClose: () => void;
  onNavigate: (href: string) => void;
};

export function CommandPalette({ actions, open, onClose, onNavigate }: CommandPaletteProps) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) {
      setQuery("");
    }
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return actions;
    }
    return actions.filter((action) => {
      const haystack = `${action.label} ${action.description}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [actions, query]);

  if (!open) {
    return null;
  }

  return (
    <div className="palette-backdrop" role="presentation" onClick={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-label="Command palette"
        onClick={(event) => event.stopPropagation()}
      >
        <input
          autoFocus
          className="palette-input"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Type a command..."
          aria-label="Search commands"
        />
        <ul className="palette-results">
          {filtered.map((action) => (
            <li key={action.id}>
              <button
                type="button"
                className="palette-item"
                onClick={() => {
                  onNavigate(action.href);
                  onClose();
                }}
              >
                <span>{action.label}</span>
                <span className="muted">{action.description}</span>
              </button>
            </li>
          ))}
          {filtered.length === 0 ? <li className="muted">No command matches.</li> : null}
        </ul>
      </div>
    </div>
  );
}
