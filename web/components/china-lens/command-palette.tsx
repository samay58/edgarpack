"use client";

import { useEffect, useMemo, useRef, useState } from "react";

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
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      restoreFocusRef.current?.focus();
      restoreFocusRef.current = null;
      return;
    }
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          "button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex='-1'])",
        ),
      );
      if (focusable.length === 0) {
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

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
        ref={dialogRef}
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(event) => event.stopPropagation()}
      >
        <input
          ref={inputRef}
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
