import { useStudio } from "../context/StudioContext";

function finquantTrainingStatusLabel(status: string | undefined): string {
  switch (status) {
    case "complete":
      return "COMPLETE";
    case "training":
      return "TRAINING";
    case "failed":
      return "FAILED";
    case "no_runs":
      return "NO RUNS";
    default:
      return status ? status.toUpperCase() : "—";
  }
}

export default function Dashboard() {
  const { domain, dashboard, dashboardErr, polling } = useStudio();
  const st = dashboard?.state_snapshot as Record<string, unknown> | undefined;
  const lf = dashboard?.legacy_finquant;
  const pct = dashboard?.progress_percent ?? 0;
  const stepLabel =
    dashboard?.progress_label ?? lf?.progress_label ?? lf?.current_step;

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
              <span className="muted">No active run</span>
            )}
          </p>
        </section>
        <section className="card wide">
          <h3>Live progress</h3>
          {domain === "finquant" ? (
            <p className="small mono accent" style={{ marginBottom: "0.35rem" }}>
              Training status:{" "}
              <strong>
                {finquantTrainingStatusLabel(dashboard?.current_status)}
              </strong>
            </p>
          ) : null}
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="mono small">
            {pct}% ·{" "}
            {domain === "finquant" && stepLabel ? (
              <>
                step <strong className="accent">{stepLabel}</strong>
                {polling ? " · syncing…" : ""}
              </>
            ) : polling ? (
              "syncing…"
            ) : (
              "idle"
            )}
          </p>
          {domain === "finquant" && lf?.log_mtime_full_train ? (
            <p className="small muted">
              Log mtime {lf.log_mtime_full_train}
            </p>
          ) : null}
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

      {domain === "finquant" && lf?.adapters_hint != null && (
        <section className="card mt">
          <h3>Adapters</h3>
          <p className="mono small">
            {lf.adapters_hint.path} — {lf.adapters_hint.count}{" "}
            {lf.adapters_hint.count === 1 ? "entry" : "entries"}
          </p>
          {lf.adapters_hint.sample?.length ? (
            <p className="mono small wrap">{lf.adapters_hint.sample.join(", ")}</p>
          ) : null}
        </section>
      )}

      {domain === "finquant" &&
      (dashboard?.training_log_tail || lf?.legacy_log_tail) ? (
        <section className="card mt">
          <h3>
            Training logs{" "}
            <span className="muted normal-case">
              (NDE run + legacy /data/finquant-1/reports)
            </span>
          </h3>
          <pre className="log-pre">
            {dashboard?.training_log_tail || lf?.legacy_log_tail || "—"}
          </pre>
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
