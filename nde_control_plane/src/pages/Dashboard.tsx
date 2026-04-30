import { useCallback, useState } from "react";
import { useStudio } from "../context/StudioContext";

function pipelineStatusLabel(status: string | undefined): string {
  if (!status) return "—";
  return status.replace(/_/g, " ").toUpperCase();
}

function jobStatusLabel(s: string | undefined): string {
  if (!s) return "—";
  return s.toUpperCase();
}

export default function Dashboard() {
  const { domain, dashboard, dashboardErr, polling, refresh } = useStudio();
  const [advancing, setAdvancing] = useState(false);
  const [advanceMsg, setAdvanceMsg] = useState<string | null>(null);
  const [fullAdminOk, setFullAdminOk] = useState(false);

  const tc = dashboard?.training_cycle;
  const aj = dashboard?.active_job;
  const pct = dashboard?.progress_percent ?? aj?.progress_percent ?? 0;
  const stepLabel =
    dashboard?.progress_label ??
    (aj?.progress_label
      ? `${aj.current_node} · ${aj.progress_label}`
      : aj?.current_node) ??
    null;

  const runAdvanceCycle = useCallback(
    async (mode: "smoke" | "full") => {
      setAdvancing(true);
      setAdvanceMsg(null);
      try {
        const body: Record<string, unknown> = { mode };
        if (mode === "full") body.admin_approved = true;
        const r = await fetch(`/api/advance/${encodeURIComponent(domain)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = (await r.json()) as Record<string, unknown>;
        if (!r.ok) {
          setAdvanceMsg(JSON.stringify(j).slice(0, 1600));
        } else {
          setAdvanceMsg(
            `Started ${String(j.run_id)} (certified baseline ${String(j.current_certified)} → candidate ${String(j.next_candidate)}). Prior certified artifacts are not modified.`
          );
        }
        await refresh();
      } catch (e) {
        setAdvanceMsg(String(e));
      } finally {
        setAdvancing(false);
      }
    },
    [domain, refresh]
  );

  const st = dashboard?.state_snapshot as Record<string, unknown> | undefined;

  return (
    <div className="page">
      <h2 className="page-title">Dashboard</h2>
      {dashboardErr && <p className="err">{dashboardErr}</p>}

      {dashboard?.active_run_id && aj ? (
        <section className="card mt wide active-job-card">
          <h3 style={{ marginTop: 0 }}>Active job</h3>
          <ul className="small mono validate-list" style={{ marginBottom: 0 }}>
            <li>
              Run ID: <strong className="accent">{aj.run_id}</strong>
            </li>
            <li>
              Status:{" "}
              <strong>{jobStatusLabel(dashboard.dashboard_status_label || aj.status)}</strong>
            </li>
            <li>
              Progress: <strong>{aj.progress_percent}%</strong>
              {aj.progress_label ? (
                <span className="muted"> · log {aj.progress_label}</span>
              ) : null}
            </li>
            <li>
              Elapsed: <strong>{aj.elapsed_display}</strong>
              {polling ? <span className="muted"> · syncing…</span> : null}
            </li>
            <li>
              Current node: <strong>{aj.current_node}</strong>
            </li>
            <li>
              Started at:{" "}
              <span className="muted">{aj.started_at ?? "—"}</span>
              {aj.derived_started_from_folder ? (
                <span className="muted"> (derived)</span>
              ) : null}
            </li>
            <li>
              Last updated: <span className="muted">{aj.last_updated ?? "—"}</span>
            </li>
            <li>
              Latest error:{" "}
              <span className={aj.latest_error ? "err-inline" : "muted"}>
                {aj.latest_error ?? "None"}
              </span>
            </li>
          </ul>
        </section>
      ) : null}

      {dashboard?.primary_run_is_cycle_candidate &&
      (dashboard.prior_certified_run_id || dashboard.prior_certified_version) ? (
        <p className="small muted mt wrap">
          Prior certified baseline (unchanged on disk):{" "}
          <span className="mono">
            {dashboard.prior_certified_version ?? "—"} (
            {dashboard.prior_certified_run_id ?? "—"})
          </span>
        </p>
      ) : null}

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
          {tc?.active_run_id &&
          tc.active_run_id !== dashboard?.active_run_id ? (
            <p className="small muted mono mt">
              Cycle blocking advance: <strong>{tc.active_run_id}</strong>
            </p>
          ) : null}
        </section>
        <section className="card wide">
          <h3>Live progress</h3>
          <p className="small mono accent" style={{ marginBottom: "0.35rem" }}>
            Pipeline:{" "}
            <strong>{pipelineStatusLabel(dashboard?.current_status)}</strong>
            {dashboard?.dashboard_status_label ? (
              <>
                {" "}
                · job{" "}
                <strong>{jobStatusLabel(dashboard.dashboard_status_label)}</strong>
              </>
            ) : null}
          </p>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="mono small">
            {pct}% ·{" "}
            {stepLabel ? (
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
        </section>
        <section className="card">
          <h3>Eval status</h3>
          <p className="mono">
            {st?.eval_passed === true ? (
              <span className="ok">PASS</span>
            ) : st?.eval_passed === false ? (
              <span className="danger">FAIL</span>
            ) : (
              <span className="muted">—</span>
            )}
          </p>
          <p className="small muted">
            Final exam:{" "}
            {st?.final_exam_passed === true
              ? "PASS"
              : st?.final_exam_passed === false
                ? "FAIL"
                : "—"}
          </p>
        </section>
        <section className="card">
          <h3>Certification</h3>
          <p className="mono">
            {st?.certified === true ? (
              <span className="ok">certified</span>
            ) : (
              <span className="muted">not certified</span>
            )}
          </p>
          <p className="small muted">{dashboard?.certification_status}</p>
        </section>
        <section className="card wide">
          <h3>Failure reason</h3>
          <p className="mono err-inline wrap">
            {dashboard?.latest_error || <span className="muted">None</span>}
          </p>
        </section>
      </div>

      {tc ? (
        <section className="card mt wide">
          <h3>Advance Training Cycle</h3>
          <p className="small muted">
            Reads certified runs from{" "}
            <span className="mono">/data/NDE/{domain}/runs/*/state.json</span>, bumps{" "}
            <span className="mono">vX.Y → vX.(Y+1)</span>, then invokes{" "}
            <span className="mono">run_graph.sh</span> only (smoke by default). No training
            execution inside this container.
          </p>
          <ul className="small mono validate-list">
            <li>
              Current certified version:{" "}
              <strong>{tc.latest_certified_version ?? "—"}</strong>{" "}
              <span className="muted">({tc.latest_certified_run_id ?? "—"})</span>
            </li>
            <li>
              Next candidate version:{" "}
              <strong>{tc.next_candidate_version ?? "—"}</strong>
            </li>
            <li>
              Active run ID (blocks advance):{" "}
              <strong>{tc.active_run_id ?? "—"}</strong>
            </li>
            <li>
              Planned run id (when advance allowed):{" "}
              <strong>{tc.next_run_id_would_be ?? "—"}</strong>
            </li>
          </ul>

          {tc.active_cycle ? (
            <div className="mt">
              <h4 className="small muted" style={{ marginBottom: "0.35rem" }}>
                Blocking candidate snapshot
              </h4>
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${tc.active_cycle.progress_percent ?? 0}%` }}
                />
              </div>
              <p className="mono small">
                {tc.active_cycle.progress_percent ?? 0}% ·{" "}
                <strong className="accent">{tc.active_cycle.current_step}</strong>
              </p>
              <p className="small mono">
                Candidate version field: {tc.active_cycle.version ?? "—"}
              </p>
              {tc.active_cycle.log_tail ? (
                <pre className="log-pre mt">{tc.active_cycle.log_tail}</pre>
              ) : null}
            </div>
          ) : null}

          <p className="small muted wrap mono">{tc.graph_entrypoint}</p>
          <div className="row-actions" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn-primary"
              disabled={advancing || !tc.can_advance}
              title={
                tc.can_advance
                  ? "POST /api/advance/:domain (smoke)"
                  : tc.advance_disabled_reason ?? "Cannot advance"
              }
              onClick={() => void runAdvanceCycle("smoke")}
            >
              {advancing ? "Starting…" : "Advance Training Cycle"}
            </button>
            <label
              className="small"
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
            >
              <input
                type="checkbox"
                checked={fullAdminOk}
                onChange={(e) => setFullAdminOk(e.target.checked)}
              />
              Admin approve full training
            </label>
            <button
              type="button"
              className="btn-ghost"
              disabled={advancing || !tc.can_advance || !fullAdminOk}
              title="Writes APPROVED and runs --mode full --require-approval"
              onClick={() => void runAdvanceCycle("full")}
            >
              Advance (full)
            </button>
          </div>
          {advanceMsg ? <p className="small mono wrap">{advanceMsg}</p> : null}
        </section>
      ) : null}

      {st?.staging_path ? (
        <section className="card mt">
          <h3>Staging</h3>
          <p className="mono small">{String(st.staging_path)}</p>
          <p className="small muted">
            Dataset ok: {String(st.dataset_ok)} · Train ok: {String(st.train_ok)}
          </p>
        </section>
      ) : null}
    </div>
  );
}
