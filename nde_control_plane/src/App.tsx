import { useCallback, useEffect, useState } from "react";

type ApiMsg = { ok?: boolean; placeholder?: boolean; message?: string; error?: string };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export default function App() {
  const [domains, setDomains] = useState<string[]>(["secops", "finquant"]);
  const [domain, setDomain] = useState("secops");
  const [adminApproval, setAdminApproval] = useState(false);
  const [runs, setRuns] = useState<string[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<Record<string, unknown> | null>(null);
  const [lastApi, setLastApi] = useState<string>("");
  const [busy, setBusy] = useState<string | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const data = await api<{ runs?: { run_id: string }[] }>(
        `/api/runs/${encodeURIComponent(domain)}`
      );
      const ids = (data.runs ?? []).map((x) => x.run_id);
      setRuns(ids);
      setLastApi(`runs/${domain}: ${ids.length} item(s)`);
    } catch (e) {
      setLastApi(`runs error: ${String(e)}`);
    }
  }, [domain]);

  useEffect(() => {
    void (async () => {
      try {
        const d = await api<{ domains?: string[] }>("/api/domains");
        if (d.domains?.length) {
          setDomains(d.domains);
          setDomain((cur) => (d.domains!.includes(cur) ? cur : d.domains![0]));
        }
      } catch {
        /* keep defaults */
      }
    })();
  }, []);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  useEffect(() => {
    if (!selectedRun) {
      setRunDetail(null);
      return;
    }
    void (async () => {
      try {
        const d = await api<Record<string, unknown>>(
          `/api/run/${encodeURIComponent(domain)}/${encodeURIComponent(selectedRun)}`
        );
        setRunDetail(d);
      } catch (e) {
        setRunDetail({ error: String(e) });
      }
    })();
  }, [domain, selectedRun]);

  const act = async (label: string, path: string, init?: RequestInit) => {
    setBusy(label);
    try {
      const j = await api<ApiMsg>(path, init);
      setLastApi(`${label}: ${JSON.stringify(j)}`);
      await refreshRuns();
    } catch (e) {
      setLastApi(`${label} failed: ${String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="app">
      <header className="banner-wrap">
        <img
          src="/finquant1/nde_studio_pattern.jpg"
          alt=""
          width={1600}
          height={200}
        />
        <div className="banner-overlay">
          <div className="banner-titles">
            <h1>NDE Studio</h1>
            <p>Control Plane</p>
          </div>
          <div className="user-box">
            <div>operator@local</div>
            <button type="button" disabled title="Placeholder">
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="toolbar">
        <label>
          Domain
          <select
            value={domain}
            onChange={(e) => {
              setDomain(e.target.value);
              setSelectedRun(null);
            }}
          >
            {domains.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!!busy}
          onClick={() => act("Upload", `/api/upload/${encodeURIComponent(domain)}`, {
            method: "POST",
            body: JSON.stringify({ files: [] }),
          })}
        >
          Upload documents
        </button>
        <button
          type="button"
          disabled={!!busy}
          onClick={() => act("Process", `/api/process/${encodeURIComponent(domain)}`, {
            method: "POST",
            body: JSON.stringify({}),
          })}
        >
          Process sources
        </button>
        <button
          type="button"
          disabled={!!busy}
          onClick={() => act("Simulate", `/api/simulate/${encodeURIComponent(domain)}`, {
            method: "POST",
            body: JSON.stringify({ mode: "simulate" }),
          })}
        >
          Run simulation
        </button>
        <button
          type="button"
          disabled={!!busy}
          onClick={() => act("Smoke train", `/api/train/${encodeURIComponent(domain)}`, {
            method: "POST",
            body: JSON.stringify({ mode: "smoke" }),
          })}
        >
          Run smoke training
        </button>
        <button
          type="button"
          disabled={!!busy || !adminApproval}
          onClick={() => act("Full train", `/api/train/${encodeURIComponent(domain)}`, {
            method: "POST",
            body: JSON.stringify({ mode: "full", require_approval: true }),
          })}
          title={!adminApproval ? "Enable admin approval first" : ""}
        >
          Run full training
        </button>
        <div className="admin-row">
          <input
            id="adm"
            type="checkbox"
            checked={adminApproval}
            onChange={(e) => setAdminApproval(e.target.checked)}
          />
          <label htmlFor="adm">Admin approval</label>
        </div>
      </div>

      <div className="panels">
        <section className="panel">
          <h2>Source files</h2>
          <p className="mono">
            Staging JSONL and uploads appear here after process wiring.
            <br />
            Domain: <span className="status-ok">{domain}</span>
          </p>
        </section>

        <section className="panel">
          <h2>Dataset status</h2>
          <p className="mono">
            Validation + SHA snapshots will bind to NDE runs under{" "}
            <code>/data/NDE</code>.
          </p>
        </section>

        <section className="panel">
          <h2>Training runs</h2>
          {runs.length === 0 ? (
            <p className="mono status-warn">No runs listed (API placeholder or empty).</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
              {runs.map((id) => (
                <li key={id}>
                  <button
                    type="button"
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--accent)",
                      cursor: "pointer",
                      textDecoration:
                        selectedRun === id ? "underline" : "none",
                    }}
                    onClick={() => setSelectedRun(id)}
                  >
                    {id}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel panel-wide">
          <h2>Selected run details</h2>
          {!selectedRun && (
            <p className="mono">Select a run from the list (placeholder data).</p>
          )}
          {selectedRun && (
            <pre className="mono">
              {runDetail ? JSON.stringify(runDetail, null, 2) : "Loading…"}
            </pre>
          )}
        </section>

        <section className="panel">
          <h2>Node proof / status</h2>
          <p className="mono">
            Graph node proofs under{" "}
            <code>runs/&lt;id&gt;/nodes/*/node_status.json</code>
          </p>
        </section>

        <section className="panel">
          <h2>Certificate status</h2>
          <p className="mono">
            <code>CERTIFICATE.json</code> when certify step completes successfully.
          </p>
        </section>

        <section className="panel panel-wide">
          <h2>Last API response</h2>
          <pre className="mono">{lastApi || "—"}</pre>
          {busy && <p className="api-note">Request: {busy}…</p>}
        </section>
      </div>
    </div>
  );
}
