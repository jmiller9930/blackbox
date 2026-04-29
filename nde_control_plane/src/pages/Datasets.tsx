import { useEffect, useState } from "react";
import { useStudio } from "../context/StudioContext";

type DatasetPayload = {
  staging_path?: string | null;
  row_count?: number | null;
  missing_source_ids?: number | null;
  adversarial_ratio?: number | null;
  latest_processor_report?: { path: string; preview: string } | null;
  source_ids_note?: string | null;
};

export default function Datasets() {
  const { domain } = useStudio();
  const [d, setD] = useState<DatasetPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await fetch(`/api/datasets/${encodeURIComponent(domain)}`);
        if (!r.ok) throw new Error(`${r.status}`);
        const j = (await r.json()) as DatasetPayload;
        if (!cancelled) setD(j);
      } catch {
        if (!cancelled) setD(null);
      }
    })();
    const t = window.setInterval(async () => {
      try {
        const r = await fetch(`/api/datasets/${encodeURIComponent(domain)}`);
        if (r.ok && !cancelled) setD(await r.json());
      } catch {
        /* */
      }
    }, 2800);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [domain]);

  return (
    <div className="page">
      <h2 className="page-title">Datasets</h2>
      <div className="grid-cards">
        <section className="card wide">
          <h3>Staging dataset path</h3>
          <p className="mono wrap">
            {d?.staging_path ?? (
              <span className="muted">No staging path in latest run state</span>
            )}
          </p>
        </section>
        <section className="card">
          <h3>Row count</h3>
          <p className="mono accent">
            {d?.row_count != null ? d.row_count : "—"}
          </p>
        </section>
        <section className="card">
          <h3>Source IDs validation</h3>
          <p className="mono">
            {d?.missing_source_ids != null
              ? `${d.missing_source_ids} missing`
              : "—"}
          </p>
          {d?.source_ids_note && (
            <p className="small muted">{d.source_ids_note}</p>
          )}
        </section>
        <section className="card">
          <h3>Adversarial ratio</h3>
          <p className="mono">
            {d?.adversarial_ratio != null
              ? `${(d.adversarial_ratio * 100).toFixed(1)}%`
              : "—"}
          </p>
        </section>
        <section className="card wide">
          <h3>Latest processor report</h3>
          {d?.latest_processor_report?.preview ? (
            <>
              <p className="mono small wrap">{d.latest_processor_report.path}</p>
              <pre className="log-pre">{d.latest_processor_report.preview}</pre>
            </>
          ) : (
            <p className="muted">No report found under domain/reports/</p>
          )}
        </section>
      </div>
    </div>
  );
}
