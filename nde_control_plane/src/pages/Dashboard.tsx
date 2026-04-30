import { useCallback, useState } from "react";
import { useStudio } from "../context/StudioContext";

function pipelineStatusLabel(status: string | undefined): string {
  if (!status) return "—";
  return status.replace(/_/g, " ").toUpperCase();
}

export default function Dashboard() {
  const { domain, dashboard, dashboardErr, polling, refresh } = useStudio();
  const [advancing, setAdvancing] = useState(false);
  const [advanceMsg, setAdvanceMsg] = useState<string | null>(null);
  const [fullAdminOk, setFullAdminOk] = useState(false);

  const tc = dashboard?.training_cycle;
  const ac = tc?.active_cycle;
  const pct = dashboard?.progress_percent ?? ac?.progress_percent ?? 0;
  const stepLabel =
    dashboard?.progress_label ?? ac?.current_step ?? null;

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
        setFullAdminOk(false);
      }
    },
    [domain, refresh]
  );

  const st = dashboard?.state_snapshot as Record<string, unknown> | undefined;

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
          {tc?.active_run_id ? (
            <p className="small muted mono mt">
              Cycle candidate: <strong>{tc.active_run_id}</strong>
            </p>
          ) : null}
        </section>
        <section className="card wide">
          <h3>Live progress</h3>
          <p className="small mono accent" style={{ marginBottom: "0.35rem" }}>
            Pipeline:{" "}
            <strong>{pipelineStatusLabel(dashboard?.current_status)}</strong>
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
            {ac?.eval_passed === true ? (
              <span className="ok">PASS</span>
            ) : ac?.eval_passed === false ? (
              <span className="danger">FAIL</span>
            ) : st?.eval_passed === true ? (
              <span className="ok">PASS</span>
            ) : st?.eval_passed === false ? (
              <span className="danger">FAIL</span>
            ) : (
              <span className="muted">—</span>
            )}
          </p>
          <p className="small muted">
            Final exam:{" "}
            {ac?.final_exam_passed === true
              ? "PASS"
              : ac?.final_exam_passed === false
                ? "FAIL"
                : st?.final_exam_passed === true
                  ? "PASS"
                  : st?.final_exam_passed === false
                    ? "FAIL"
                    : "—"}
          </p>
        </section>
        <section className="card">
          <h3>Certification</h3>
          <p className="mono">
            {ac?.certified === true || st?.certified === true ? (
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
            {ac?.last_error ||
              dashboard?.latest_error || (
                <span className="muted">None</span>
              )}
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
              Active run ID:{" "}
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
                Active candidate snapshot
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
            <label className="small" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
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
