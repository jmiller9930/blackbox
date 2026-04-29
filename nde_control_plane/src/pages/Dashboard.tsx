import { useStudio } from "../context/StudioContext";

export default function Dashboard() {
  const { domain, dashboard, dashboardErr, polling } = useStudio();
  const st = dashboard?.state_snapshot as Record<string, unknown> | undefined;
  const pct = dashboard?.progress_percent ?? 0;

  return (
    <div className="page">
      <h2 className="page-title">Dashboard</h2>
      {dashboardErr && <p className="err">{dashboardErr}</p>}
      <div className="grid-cards">
        <section className="card">
          <h3>Selected domain</h3>
          <p className="mono accent">{domain}</p>
        </section>
        <section className="card">
          <h3>Active / latest run</h3>
          <p className="mono">
            {dashboard?.active_run_id ?? (
              <span className="muted">No runs under /data/NDE yet</span>
            )}
          </p>
        </section>
        <section className="card wide">
          <h3>Live progress</h3>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="mono small">{pct}% · {polling ? "syncing…" : "idle"}</p>
        </section>
        <section className="card">
          <h3>Current status</h3>
          <p className="mono">{dashboard?.current_status ?? "—"}</p>
        </section>
        <section className="card">
          <h3>Latest error</h3>
          <p className="mono err-inline">
            {dashboard?.latest_error || (
              <span className="muted">None</span>
            )}
          </p>
        </section>
        <section className="card">
          <h3>Certification</h3>
          <p className="mono">
            {dashboard?.certificate_on_disk ? (
              <span className="ok">CERTIFICATE.json present</span>
            ) : st?.certified ? (
              <span className="ok">State marked certified</span>
            ) : (
              <span className="muted">No certificate</span>
            )}
          </p>
          <p className="small muted">{dashboard?.certification_status}</p>
        </section>
      </div>

      {domain === "finquant" && dashboard?.training_log_tail ? (
        <section className="card mt">
          <h3>Training log (latest run)</h3>
          <pre className="log-pre">{dashboard.training_log_tail}</pre>
        </section>
      ) : null}

      {domain === "secops" && st?.staging_path ? (
        <section className="card mt">
          <h3>SecOps staging</h3>
          <p className="mono small">{String(st.staging_path)}</p>
          <p className="small muted">
            Dataset ok: {String(st.dataset_ok)} · Train ok:{" "}
            {String(st.train_ok)}
          </p>
        </section>
      ) : null}
    </div>
  );
}
