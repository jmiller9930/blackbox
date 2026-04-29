import { useEffect, useState } from "react";
import { useStudio } from "../context/StudioContext";

type RunDetail = {
  state?: Record<string, unknown> | null;
  certificate_present?: boolean;
  nodes?: { node?: string; status?: string }[];
  log_tail?: string;
};

export default function Runs() {
  const { domain, runs, selectedRunId, setSelectedRunId } = useStudio();
  const [detail, setDetail] = useState<RunDetail | null>(null);

  useEffect(() => {
    if (!selectedRunId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch(
          `/api/run/${encodeURIComponent(domain)}/${encodeURIComponent(selectedRunId)}`
        );
        if (!r.ok) throw new Error(`${r.status}`);
        const j = (await r.json()) as RunDetail;
        if (!cancelled) setDetail(j);
      } catch {
        if (!cancelled) setDetail(null);
      }
    };
    void load();
    const t = window.setInterval(load, 2600);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [domain, selectedRunId]);

  return (
    <div className="page">
      <h2 className="page-title">Runs</h2>
      <div className="runs-split">
        <aside className="run-list">
          <h3>Run list</h3>
          {!runs.length ? (
            <p className="muted small">No runs.</p>
          ) : (
            <ul className="run-ul">
              {runs.map((id) => (
                <li key={id}>
                  <button
                    type="button"
                    className={
                      selectedRunId === id ? "run-pick active" : "run-pick"
                    }
                    onClick={() => setSelectedRunId(id)}
                  >
                    {id}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <div className="run-detail">
          {!selectedRunId ? (
            <p className="muted">Select a run.</p>
          ) : (
            <>
              <section className="card">
                <h3>state.json</h3>
                <pre className="json-pre">
                  {detail?.state
                    ? JSON.stringify(detail.state, null, 2)
                    : "Loading…"}
                </pre>
              </section>
              <section className="card mt">
                <h3>Node statuses</h3>
                {!detail?.nodes?.length ? (
                  <p className="muted">No node proofs.</p>
                ) : (
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Node</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.nodes.map((n) => (
                        <tr key={String(n.node)}>
                          <td className="mono">{String(n.node)}</td>
                          <td>{String(n.status ?? "—")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
              <section className="card mt">
                <h3>Training / graph log tail</h3>
                <pre className="log-pre">{detail?.log_tail || "—"}</pre>
              </section>
              <section className="card mt">
                <h3>Certificate</h3>
                <p className="mono">
                  {detail?.certificate_present ? (
                    <span className="ok">CERTIFICATE.json on disk</span>
                  ) : (
                    <span className="muted">No certificate file</span>
                  )}
                </p>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
