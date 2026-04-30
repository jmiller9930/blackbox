import { useCallback, useState } from "react";
import { useStudio } from "../context/StudioContext";

function finquantTrainingStatusLabel(status: string | undefined): string {
  switch (status) {
    case "complete":
      return "COMPLETE";
    case "certified":
      return "CERTIFIED";
    case "training":
      return "TRAINING";
    case "failed":
      return "FAILED";
    case "eval_failed":
      return "EVAL FAILED";
    case "validation_failed":
      return "VALIDATION FAILED";
    case "no_runs":
      return "NO RUNS";
    default:
      return status ? status.toUpperCase() : "—";
  }
}

export default function Dashboard() {
  const { domain, dashboard, dashboardErr, polling, refresh } = useStudio();
  const [validating, setValidating] = useState(false);
  const [validateMsg, setValidateMsg] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [advanceMsg, setAdvanceMsg] = useState<string | null>(null);
  const [fullAdminOk, setFullAdminOk] = useState(false);

  const tc = dashboard?.training_cycle;

  const runAdvanceCycle = useCallback(
    async (mode: "smoke" | "full") => {
      setAdvancing(true);
      setAdvanceMsg(null);
      try {
        const body: Record<string, unknown> = { mode };
        if (mode === "full") body.admin_approved = true;
        const r = await fetch(
          `/api/nde/advance-cycle/${encodeURIComponent(domain)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        const j = (await r.json()) as Record<string, unknown>;
        if (!r.ok) {
          setAdvanceMsg(JSON.stringify(j).slice(0, 1600));
        } else {
          setAdvanceMsg(
            `LangGraph started (${String(j.mode)}): ${String(j.run_id)} · prior certified run ${String(j.prior_certified_run_id)} unchanged on disk.`
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

  const runValidateV02 = useCallback(async () => {
    setValidating(true);
    setValidateMsg(null);
    try {
      const r = await fetch("/api/finquant/validate-v02", { method: "POST" });
      const j = (await r.json()) as {
        ok?: boolean;
        error?: string;
        step?: string;
        certified?: boolean;
      };
      if (!r.ok) {
        setValidateMsg(
          `${j.step ?? "error"}: ${j.error ?? r.statusText}`.slice(0, 800)
        );
      } else {
        setValidateMsg(
          j.certified
            ? "Validation finished: certified."
            : "Validation finished: eval did not certify (see state / report)."
        );
      }
      await refresh();
    } catch (e) {
      setValidateMsg(String(e));
    } finally {
      setValidating(false);
    }
  }, [refresh]);
  const st = dashboard?.state_snapshot as Record<string, unknown> | undefined;
  const lf = dashboard?.legacy_finquant;
  const fqV02 = dashboard?.finquant_v02;
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

      {tc ? (
        <section className="card mt wide">
          <h3>Advance Training Cycle</h3>
          <p className="small muted">
            Detects the latest <strong>certified</strong> version from{" "}
            <span className="mono">/data/NDE/{domain}/runs/*/state.json</span>, bumps{" "}
            <span className="mono">v0.N → v0.N+1</span>, then starts{" "}
            <span className="mono">run_graph.sh</span> (LangGraph only). Smoke training is default;
            full training requires explicit admin approval below.
          </p>
          <ul className="small mono validate-list">
            <li>
              Current certified version:{" "}
              <strong>{tc.latest_certified_version ?? "—"}</strong> (
              {tc.latest_certified_run_id ?? "—"})
            </li>
            <li>
              Next candidate version: <strong>{tc.next_candidate_version ?? "—"}</strong>
            </li>
            <li>
              Planned run id (when advance is allowed):{" "}
              <strong>{tc.next_run_id_would_be ?? "—"}</strong>
            </li>
            <li>
              Active / blocking candidate:{" "}
              {tc.active_blocking_candidate ? (
                <span className="warn">
                  {tc.active_blocking_candidate.run_id} — {tc.active_blocking_candidate.reason}{" "}
                  {tc.active_blocking_candidate.detail
                    ? `(${tc.active_blocking_candidate.detail})`
                    : ""}
                </span>
              ) : (
                <span className="muted">none</span>
              )}
            </li>
            <li>
              Eval (latest dashboard snapshot):{" "}
              <strong>
                {st?.eval_passed === true
                  ? "PASS"
                  : st?.eval_passed === false
                    ? "FAIL"
                    : "—"}
              </strong>{" "}
              · Final exam:{" "}
              <strong>
                {st?.final_exam_passed === true
                  ? "PASS"
                  : st?.final_exam_passed === false
                    ? "FAIL"
                    : "—"}
              </strong>{" "}
              · Certified:{" "}
              <strong className={st?.certified ? "ok" : "muted"}>
                {String(!!st?.certified)}
              </strong>
            </li>
          </ul>
          <p className="small muted wrap mono">{tc.graph_entrypoint}</p>
          <div className="row-actions" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn-primary"
              disabled={advancing || !tc.can_advance}
              title={
                tc.can_advance
                  ? "Start smoke cycle via LangGraph"
                  : tc.advance_disabled_reason ?? "Cannot advance"
              }
              onClick={() => void runAdvanceCycle("smoke")}
            >
              {advancing ? "Starting…" : "Advance Training Cycle (smoke)"}
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
              title="Creates APPROVED in the new run dir and invokes --mode full --require-approval"
              onClick={() => void runAdvanceCycle("full")}
            >
              Advance (full)
            </button>
          </div>
          {advanceMsg ? <p className="small mono wrap">{advanceMsg}</p> : null}
        </section>
      ) : null}

      {domain === "finquant" && (
        <section className="card mt">
          <h3>Legacy FinQuant v0.2 validation</h3>
          <p className="small muted">
            Optional path: checks adapter, training proof (<span className="mono">train_runtime</span>{" "}
            + steps), then runs host script{" "}
            <span className="mono">/data/NDE/tools/run_finquant_v02_eval.sh</span> (Python + GPU on
            the host via <span className="mono">TRAIN_PYTHON</span>, not inside the Node container).
            Prefer <strong>Advance Training Cycle</strong> for new semver bumps via LangGraph.
          </p>
          <p>
            <button
              type="button"
              className="btn-primary"
              disabled={validating}
              onClick={() => void runValidateV02()}
            >
              {validating ? "Validating…" : "Validate v0.2"}
            </button>
          </p>
          {validateMsg ? <p className="small mono wrap">{validateMsg}</p> : null}
        </section>
      )}

      {domain === "finquant" && fqV02 && (
        <section className="card mt">
          <h3>v0.2 validation result</h3>
          <ul className="small mono validate-list">
            <li>
              Training complete:{" "}
              <strong className={fqV02.train_complete ? "ok" : "danger"}>
                {fqV02.train_complete ? "yes" : "no"}
              </strong>
            </li>
            <li>
              Eval:{" "}
              <strong className={fqV02.eval_passed ? "ok" : "danger"}>
                {fqV02.eval_passed ? "PASS" : "FAIL"}
              </strong>
            </li>
            <li>
              Score: {fqV02.score_label ?? "—"}
            </li>
            <li>
              Certification:{" "}
              <strong className={fqV02.certified ? "ok" : "warn"}>
                {fqV02.certified ? "certified" : "not certified"}
              </strong>
            </li>
            <li className="wrap">State: {fqV02.state_path}</li>
            <li className="wrap">Eval report: {fqV02.eval_report_path ?? "—"}</li>
            {fqV02.validated_at ? (
              <li className="muted">Validated at: {fqV02.validated_at}</li>
            ) : null}
            {fqV02.last_error ? (
              <li className="err-inline wrap">Last error: {fqV02.last_error}</li>
            ) : null}
          </ul>
        </section>
      )}

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
