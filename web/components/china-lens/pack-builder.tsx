"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { createPack, getPackStatus } from "@/lib/api-client";
import type { PackStatusResponse } from "@/types/china-lens";

const STAGES = ["download", "extract", "translate", "summarize", "index"] as const;

type PackBuilderProps = {
  companyId: string;
};

export function PackBuilder({ companyId }: PackBuilderProps) {
  const [packId, setPackId] = useState<string | null>(null);
  const [status, setStatus] = useState<PackStatusResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (!packId || status?.status === "completed" || status?.status === "failed") {
      return;
    }

    let canceled = false;
    const tick = async () => {
      const next = await getPackStatus(packId);
      if (!canceled && next) {
        setStatus(next);
      }
    };

    tick();
    const interval = window.setInterval(tick, 1200);
    return () => {
      canceled = true;
      window.clearInterval(interval);
    };
  }, [packId, status?.status]);

  const onCreatePack = () => {
    setError("");
    startTransition(async () => {
      const created = await createPack(companyId);
      if (!created) {
        setError("Unable to create a pack. Confirm the China Lens API is running.");
        return;
      }
      setPackId(created.pack_id);
      setStatus(null);
    });
  };

  const canOpenPack = Boolean(packId && status?.status === "completed");

  return (
    <section className="panel">
      <div className="row between">
        <h2>Pack Builder</h2>
        <button type="button" className="primary-btn" onClick={onCreatePack} disabled={isPending}>
          {isPending ? "Starting..." : "Generate Pack"}
        </button>
      </div>
      <p className="muted">Build citation-backed sections from indexed filings.</p>
      <div className="builder-grid">
        <label>
          Company
          <input value={companyId} readOnly />
        </label>
        <label>
          Time Range
          <input value="Last annual + last 2 interim" readOnly />
        </label>
        <label>
          Translation Mode
          <input value="Key sections only" readOnly />
        </label>
        <label>
          Template
          <input value="Investor diligence" readOnly />
        </label>
      </div>
      <ol className="stage-list">
        {STAGES.map((stage) => (
          <li key={stage} className={status?.stage === stage ? "active" : ""}>
            <span>{stage}</span>
            <small>{status?.stage_progress[stage] ?? 0}%</small>
          </li>
        ))}
      </ol>
      {status ? (
        <p className="muted" aria-live="polite">
          {status.status} · {status.progress_pct}%
        </p>
      ) : null}
      {error ? (
        <p className="muted" role="alert">
          {error}
        </p>
      ) : null}
      {canOpenPack && packId ? (
        <Link href={`/${companyId}/packs/${packId}`} className="secondary-btn link-btn">
          Open Pack
        </Link>
      ) : null}
    </section>
  );
}
