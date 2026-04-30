import {
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DASHBOARD_BLOCK_ORDER_DEFAULT,
  loadDashboardBlockOrder,
  mergeVisibleBlockOrder,
  saveDashboardBlockOrder,
  getVisibleDashboardBlockIds,
  type DashboardBlockId,
} from "../dashboardBlockOrder";
import { SortableDashboardBlock } from "../SortableDashboardBlock";
import { CollapsibleDashboardSection } from "../CollapsibleDashboardSection";
import {
  useStudio,
  type SystemPosture,
  type TrainingTelemetryPayload,
} from "../context/StudioContext";

function pipelineStatusLabel(status: string | undefined): string {
  if (!status) return "—";
  return status.replace(/_/g, " ").toUpperCase();
}

function jobStatusLabel(s: string | undefined): string {
  if (!s) return "—";
  return s.toUpperCase();
}

function formatTelemetryMetric(n: number | null | undefined, digits = 4): string {
  if (n == null || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  const d = abs >= 1000 ? 0 : abs >= 1 ? Math.min(4, digits) : Math.min(6, digits);
  return n.toFixed(d).replace(/\.?0+$/, "");
}

function renderTelemetryRows(tt: TrainingTelemetryPayload) {
  const gpuLine =
    tt.gpu_name?.trim() ||
    "GPU telemetry unavailable";
  const vramLine = tt.vram_used?.trim() || "—";
  const utilLine = tt.gpu_utilization?.trim() || "—";
  const hasParsedSteps =
    tt.train_step_current != null &&
    tt.train_step_total != null;

  return (
    <ul className="small mono validate-list" style={{ marginBottom: 0 }}>
      {tt.operator_headline ? (
        <li className="wrap">
          <strong className="accent">{tt.operator_headline}</strong>
        </li>
      ) : null}
      {tt.operator_detail ? (
        <li className="muted wrap">{tt.operator_detail}</li>
      ) : null}
      <li>
        Run mode: <strong>FULL</strong>
      </li>
      <li>
        Domain: <strong className="accent">{tt.domain}</strong>
      </li>
      <li>
        Version: <strong>{tt.version}</strong>
      </li>
      <li className="wrap">
        Dataset: <span className="accent">{tt.dataset_path || "—"}</span>
      </li>
      <li>
        Dataset source: <strong>{tt.dataset_resolution_source}</strong>
      </li>
      <li>
        Rows: <strong>{tt.dataset_rows}</strong>
      </li>
      <li className="wrap">
        Base model: <span className="muted">{tt.base_model ?? "—"}</span>
      </li>
      <li className="wrap">
        Adapter output: <span className="muted">{tt.adapter_output ?? "—"}</span>
      </li>
      <li>
        Checkpoint shards:{" "}
        <strong>
          {tt.checkpoint_shards_loaded} / {tt.checkpoint_shards_total}
        </strong>
      </li>
      {hasParsedSteps ? (
        <>
          <li>
            Step:{" "}
            <strong>
              {tt.train_step_current} / {tt.train_step_total}
            </strong>
          </li>
          <li>
            Progress:{" "}
            <strong>
              {tt.progress_percent != null ? `${tt.progress_percent}%` : "calculating"}
            </strong>
          </li>
        </>
      ) : tt.training_initializing === true ? (
        <>
          <li>
            Step: <strong>waiting for trainer output</strong>
          </li>
          <li>
            Progress: <strong>—</strong>
          </li>
        </>
      ) : (
        <>
          <li>
            Step: <strong>not yet parsed from logs</strong>
          </li>
          <li>
            Progress: <strong>—</strong>
          </li>
        </>
      )}
      <li>
        Epoch: <strong>{formatTelemetryMetric(tt.epoch, 2)}</strong>
      </li>
      <li>
        Loss: <strong>{formatTelemetryMetric(tt.loss)}</strong>
      </li>
      <li>
        LR: <strong>{formatTelemetryMetric(tt.learning_rate)}</strong>
      </li>
      <li>
        Token accuracy:{" "}
        <strong>{formatTelemetryMetric(tt.mean_token_accuracy)}</strong>
      </li>
      {tt.gpu_status_hint ? (
        <li className="muted wrap">
          <strong>{tt.gpu_status_hint}</strong>
        </li>
      ) : null}
      <li>
        GPU: <strong>{gpuLine}</strong>
      </li>
      <li>
        VRAM: <strong>{vramLine}</strong>
      </li>
      <li>
        GPU util: <strong>{utilLine}</strong>
      </li>
      <li>
        Elapsed: <strong>{tt.elapsed}</strong>
      </li>
      <li>
        ETA: <strong>{tt.eta}</strong>
      </li>
    </ul>
  );
}

/** Always-visible strip: same step / total / % as terminal tqdm when logs parse. */
function TrainingStepsHero({ tt }: { tt: TrainingTelemetryPayload }) {
  const cur = tt.train_step_current;
  const tot = tt.train_step_total;
  const pct =
    tt.progress_percent ??
    (cur != null && tot != null && tot > 0
      ? Math.round((cur / tot) * 10000) / 100
      : null);
  const cfgMax = tt.config_max_steps_full;

  if (cur != null && tot != null && tot > 0) {
    return (
      <>
        <div className="training-steps-hero-main mono">
          Step <strong className="accent">{cur}</strong> / <strong>{tot}</strong>
          {pct != null ? (
            <>
              {" "}
              · <strong>{pct}%</strong> complete
            </>
          ) : null}
        </div>
        <p className="small muted mono" style={{ margin: "0.4rem 0 0" }}>
          Parsed from live trainer logs (same style as{" "}
          <span className="accent">123/3000</span> in the terminal).
        </p>
      </>
    );
  }

  return (
    <>
      <div className="training-steps-hero-main mono">
        Step <strong className="accent">—</strong> / <strong>—</strong>
        {cfgMax != null ? (
          <>
            {" "}
            <span className="muted">
              (full run <strong>max_steps</strong> in config:{" "}
              <strong className="accent">{cfgMax}</strong>)
            </span>
          </>
        ) : null}
      </div>
      <p className="small muted mono wrap" style={{ margin: "0.4rem 0 0" }}>
        Percent and exact position appear here once stdout/stderr contains a fraction like{" "}
        <span className="accent">2097/3000</span>. Also open{" "}
        <strong>Training telemetry</strong> (below) for the full list + log tail.
      </p>
    </>
  );
}

function systemPostureHeading(posture: SystemPosture | undefined): string {
  switch (posture) {
    case "RUNNING":
      return "Running";
    case "BLOCKED":
      return "Blocked";
    case "FAILED":
      return "Failed";
    case "NO_ACTIVE_JOB":
    default:
      return "No active job running";
  }
}

export default function Dashboard() {
  const { domain, dashboard, dashboardErr, polling, refresh } = useStudio();
  const [advancing, setAdvancing] = useState(false);
  const [advanceMsg, setAdvanceMsg] = useState<string | null>(null);
  const [fullAdminOk, setFullAdminOk] = useState(false);
  const [orderedBlockIds, setOrderedBlockIds] = useState<DashboardBlockId[]>([]);

  const tc = dashboard?.training_cycle;
  const aj = dashboard?.active_job;
  const execId = dashboard?.execution_active_run_id ?? null;
  const featuredId = dashboard?.featured_run_id ?? dashboard?.active_run_id ?? null;
  const posture = dashboard?.system_posture ?? "NO_ACTIVE_JOB";
  const statusLines = dashboard?.system_status_lines ?? [];
  const pollLive = !!(polling && execId);

  const isTrainingPhase = dashboard?.dashboard_status_label === "TRAINING";
  const pctLegacy =
    dashboard?.progress_percent != null
      ? dashboard.progress_percent
      : aj?.progress_percent != null
        ? aj.progress_percent
        : 0;

  const st = dashboard?.state_snapshot as Record<string, unknown> | undefined;

  const visibleBlockIds = useMemo(
    () =>
      getVisibleDashboardBlockIds({
        dashboard,
        execId,
        aj,
        featuredId,
        tc,
        st,
      }),
    [
      dashboard,
      execId,
      aj,
      featuredId,
      tc,
      st,
    ]
  );

  const visibleSig = visibleBlockIds.join(",");

  useEffect(() => {
    const saved = loadDashboardBlockOrder(domain);
    setOrderedBlockIds(
      mergeVisibleBlockOrder(saved, visibleBlockIds, DASHBOARD_BLOCK_ORDER_DEFAULT)
    );
  }, [domain, visibleSig]);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const onDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;
      setOrderedBlockIds((items) => {
        const oldIndex = items.indexOf(active.id as DashboardBlockId);
        const newIndex = items.indexOf(over.id as DashboardBlockId);
        if (oldIndex < 0 || newIndex < 0) return items;
        const next = arrayMove(items, oldIndex, newIndex);
        saveDashboardBlockOrder(domain, next);
        return next;
      });
    },
    [domain]
  );

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

  const renderBlock = (blockId: DashboardBlockId) => {
    switch (blockId) {
      case "system-status":
        return (
          <CollapsibleDashboardSection
            panelKey={`${domain}:system-status`}
            title="System status"
            className="card wide system-status-card"
          >
            <p className="mono accent" style={{ marginBottom: "0.5rem", marginTop: 0 }}>
              {systemPostureHeading(posture)}
            </p>
            {statusLines.length > 0 ? (
              <ul className="small mono validate-list" style={{ marginBottom: 0 }}>
                {statusLines.map((line, i) => (
                  <li key={`${i}-${line.slice(0, 24)}`}>{line}</li>
                ))}
              </ul>
            ) : null}
          </CollapsibleDashboardSection>
        );

      case "training-telemetry": {
        const tt = dashboard?.training_telemetry;
        if (
          !tt ||
          !execId ||
          dashboard?.dashboard_status_label !== "TRAINING"
        ) {
          return null;
        }
        return (
          <CollapsibleDashboardSection
            panelKey={`${domain}:training-telemetry`}
            title="Training telemetry"
            className="card wide training-telemetry-card"
          >
            <p className="mono accent" style={{ marginBottom: "0.5rem", marginTop: 0 }}>
              Live full-training metrics (updates every ~2s)
            </p>
            {renderTelemetryRows(tt)}
            {tt.log_tail ? (
              <details className="collapse-details mt">
                <summary className="collapse-summary">Log tail</summary>
                <pre className="mono small log-tail-pre wrap">{tt.log_tail}</pre>
              </details>
            ) : null}
          </CollapsibleDashboardSection>
        );
      }

      case "certified-summary":
        if (!dashboard?.certified_feature_summary) return null;
        return (
          <CollapsibleDashboardSection
            panelKey={`${domain}:certified-summary`}
            title="Latest certified run"
            className="card wide certified-summary-card"
          >
            <ul className="small mono validate-list" style={{ marginBottom: 0, marginTop: 0 }}>
              <li>
                Run ID:{" "}
                <strong className="accent">
                  {dashboard.certified_feature_summary.run_id}
                </strong>
              </li>
              <li>
                Status: <strong>CERTIFIED</strong>
              </li>
              <li>
                Duration:{" "}
                <strong>{dashboard.certified_feature_summary.duration_display}</strong>
              </li>
              <li>
                Completed:{" "}
                <span className="muted">
                  {dashboard.certified_feature_summary.completed_at ?? "—"}
                </span>
              </li>
            </ul>
          </CollapsibleDashboardSection>
        );

      case "job-in-progress":
        if (!execId || !aj || !dashboard) return null;
        return (
          <CollapsibleDashboardSection
            panelKey={`${domain}:job-in-progress`}
            title="Job in progress"
            className="card wide active-job-card"
          >
            <ul className="small mono validate-list" style={{ marginBottom: 0, marginTop: 0 }}>
              <li>
                Run ID: <strong className="accent">{aj.run_id}</strong>
              </li>
              <li>
                Status:{" "}
                <strong>{jobStatusLabel(dashboard.dashboard_status_label || aj.status)}</strong>
              </li>
              <li>
                Pipeline stage:{" "}
                <strong>{aj.pipeline_stage_label ?? dashboard.pipeline_focus_label ?? "—"}</strong>
              </li>
              {aj.operator_headline ? (
                <li className="wrap">
                  Status: <strong className="accent">{aj.operator_headline}</strong>
                </li>
              ) : null}
              {aj.operator_detail ? (
                <li className="muted wrap">{aj.operator_detail}</li>
              ) : null}
              <li>
                Training progress:{" "}
                <strong>{aj.training_progress_detail ?? "—"}</strong>
              </li>
              <li>
                Training bar:{" "}
                <strong>
                  {aj.training_progress_indeterminate
                    ? "indeterminate (GPU / logs active, or waiting for step lines)"
                    : aj.training_progress_bar_percent != null
                      ? `${aj.training_progress_bar_percent}%`
                      : aj.progress_percent != null
                        ? `${aj.progress_percent}%`
                        : "—"}
                </strong>
                {(aj.training_eta_hint ?? aj.progress_label) ? (
                  <span className="muted">
                    {" "}
                    · ETA / pace: {aj.training_eta_hint ?? aj.progress_label}
                  </span>
                ) : null}
              </li>
              <li>
                Elapsed: <strong>{aj.elapsed_display}</strong>
                {pollLive ? <span className="muted"> · syncing…</span> : null}
              </li>
              <li>
                Pipeline detail:{" "}
                <strong>{dashboard.pipeline_focus_label ?? "—"}</strong>
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
          </CollapsibleDashboardSection>
        );

      case "pipeline-detail":
        if (
          !featuredId ||
          !dashboard ||
          (dashboard.pipeline_steps?.length ?? 0) === 0
        ) {
          return null;
        }
        return (
          <CollapsibleDashboardSection
            panelKey={`${domain}:pipeline-detail`}
            title="Pipeline detail"
            className="card wide pipeline-detail-card"
          >
                {dashboard.version_flow ? (
                  <p
                    className="small mono accent wrap"
                    style={{ marginBottom: "0.75rem", marginTop: 0 }}
                  >
                    {dashboard.version_flow}
                  </p>
                ) : null}
                <p className="mono small" style={{ marginBottom: "0.75rem" }}>
                  <strong>{dashboard.pipeline_focus_label ?? "—"}</strong>
                </p>

                <details className="collapse-details">
                  <summary className="collapse-summary">Node timeline</summary>
                  <ul className="small mono validate-list pipeline-timeline">
                    {(dashboard.pipeline_timeline_lines ?? []).map((line, i) => (
                      <li key={`${i}-${line}`}>{line}</li>
                    ))}
                  </ul>
                </details>

                {(dashboard.pipeline_timing_lines?.length ?? 0) > 0 ? (
                  <details className="collapse-details">
                    <summary className="collapse-summary">Node timing</summary>
                    <ul className="small mono validate-list">
                      {(dashboard.pipeline_timing_lines ?? []).map((line, i) => (
                        <li key={`${i}-${line}`}>{line}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}

                {dashboard.actionable_error ? (
                  <>
                    <h4 className="small muted mt" style={{ marginBottom: "0.35rem" }}>
                      Actionable guidance
                    </h4>
                    <dl className="actionable-dl small">
                      <dt className="muted">Problem</dt>
                      <dd>{dashboard.actionable_error.problem}</dd>
                      {dashboard.actionable_error.expected ? (
                        <>
                          <dt className="muted">Expected</dt>
                          <dd className="mono wrap">{dashboard.actionable_error.expected}</dd>
                        </>
                      ) : null}
                      <dt className="muted">Fix</dt>
                      <dd>{dashboard.actionable_error.fix}</dd>
                      <dt className="muted">Next action</dt>
                      <dd>{dashboard.actionable_error.next_action}</dd>
                    </dl>
                  </>
                ) : null}

                {dashboard.current_node_artifacts ? (
                  <details className="collapse-details">
                    <summary className="collapse-summary">
                      Current / failed node artifacts (
                      {dashboard.current_node_artifacts.graph_node})
                    </summary>
                    <p className="small muted" style={{ marginBottom: "0.25rem" }}>
                      Inputs
                    </p>
                    <ul className="small mono validate-list">
                      {dashboard.current_node_artifacts.inputs.map((x) => (
                        <li key={x}>{x}</li>
                      ))}
                    </ul>
                    <p className="small muted mt" style={{ marginBottom: "0.25rem" }}>
                      Outputs
                    </p>
                    <ul className="small mono validate-list">
                      {dashboard.current_node_artifacts.outputs.map((x) => (
                        <li key={x}>{x}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
          </CollapsibleDashboardSection>
        );

      case "prior-baseline":
        if (
          !dashboard?.primary_run_is_cycle_candidate ||
          !(dashboard.prior_certified_run_id || dashboard.prior_certified_version)
        ) {
          return null;
        }
        return (
          <CollapsibleDashboardSection
            panelKey={`${domain}:prior-baseline`}
            title="Prior certified baseline"
            className="card wide"
          >
            <p className="small muted wrap" style={{ margin: 0 }}>
              Unchanged on disk:{" "}
              <span className="mono">
                {dashboard.prior_certified_version ?? "—"} (
                {dashboard.prior_certified_run_id ?? "—"})
              </span>
            </p>
          </CollapsibleDashboardSection>
        );

      case "summary-grid":
        return (
          <CollapsibleDashboardSection
            panelKey={`${domain}:summary-grid`}
            title="Summary & progress"
            className="card wide"
          >
          <div className="grid-cards">
            <section className="card">
              <h3>Selected domain</h3>
              <p className="mono accent">{domain}</p>
            </section>
            <section className="card">
              <h3>Featured run</h3>
              <p className="mono accent">
                {featuredId ?? <span className="muted">None</span>}
              </p>
              {execId ? (
                <p className="small muted mt">
                  Execution: <strong className="mono">{execId}</strong>
                </p>
              ) : null}
              {tc?.active_run_id && tc.active_run_id !== featuredId ? (
                <p className="small muted mono mt">
                  Cycle blocking advance: <strong>{tc.active_run_id}</strong>
                </p>
              ) : null}
            </section>
            <section className="card wide">
              <h3>{execId ? "Live progress" : "Progress snapshot"}</h3>
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
              {execId ? (
                isTrainingPhase && aj ? (
                  <>
                    {aj.operator_headline ? (
                      <p className="mono small accent wrap" style={{ marginBottom: "0.35rem" }}>
                        {aj.operator_headline}
                      </p>
                    ) : null}
                    {aj.pipeline_stage_label ? (
                      <p className="mono small" style={{ marginBottom: "0.35rem" }}>
                        Pipeline stage:{" "}
                        <strong className="accent">{aj.pipeline_stage_label}</strong>
                      </p>
                    ) : null}
                    <p className="mono small" style={{ marginBottom: "0.5rem" }}>
                      Training progress:{" "}
                      <strong className="accent">
                        {aj.training_progress_detail ?? "—"}
                      </strong>
                      {aj.training_progress_bar_percent != null &&
                      !aj.training_progress_indeterminate ? (
                        <span className="muted">
                          {" "}
                          ({aj.training_progress_bar_percent}%)
                        </span>
                      ) : null}
                    </p>
                    {aj.training_progress_indeterminate ? (
                      <div
                        className="progress-bar progress-bar-indeterminate"
                        role="progressbar"
                        aria-valuetext={
                          aj.operator_headline ?? "Training in progress"
                        }
                      />
                    ) : (
                      <>
                        <div className="progress-bar">
                          <div
                            className="progress-fill"
                            style={{
                              width: `${Math.min(100, aj.training_progress_bar_percent ?? 0)}%`,
                            }}
                          />
                        </div>
                        {aj.training_progress_bar_percent != null ? (
                          <p className="mono small muted" style={{ marginTop: "0.35rem" }}>
                            Percent:{" "}
                            <strong>{aj.training_progress_bar_percent}%</strong> (from trainer
                            steps)
                          </p>
                        ) : null}
                      </>
                    )}
                    <p className="mono small" style={{ marginTop: "0.35rem" }}>
                      {aj.training_live_summary ?? "—"}
                      {pollLive ? <span className="muted"> · syncing…</span> : null}
                    </p>
                    {dashboard?.progress_label &&
                    dashboard.progress_label !== "ETA: calculating" ? (
                      <p className="mono small muted" style={{ marginTop: "0.35rem" }}>
                        ETA: <strong>{dashboard.progress_label}</strong>
                      </p>
                    ) : null}
                  </>
                ) : (
                  <>
                    <div className="progress-bar">
                      <div
                        className="progress-fill"
                        style={{ width: `${pctLegacy}%` }}
                      />
                    </div>
                    <p className="mono small">
                      {pctLegacy}% ·{" "}
                      <strong className="accent">
                        {dashboard?.progress_label ??
                          (aj?.progress_label
                            ? `${aj.current_node} · ${aj.progress_label}`
                            : aj?.current_node) ??
                          "—"}
                      </strong>
                      {pollLive ? <span className="muted"> · syncing…</span> : null}
                    </p>
                  </>
                )
              ) : (
                <>
                  <div
                    className="progress-bar progress-bar-idle"
                    role="img"
                    aria-label="Standing by — no job executing"
                  >
                    <span className="progress-idle-inner">Standing by</span>
                  </div>
                  <p className="mono small muted">
                    No job executing.
                    {featuredId && dashboard?.dashboard_status_label ? (
                      <>
                        {" "}
                        Last featured snapshot:{" "}
                        <strong className="accent">
                          {jobStatusLabel(dashboard.dashboard_status_label)}
                        </strong>
                        {dashboard.dashboard_status_label === "CERTIFIED" ? (
                          <span> — run complete (historical)</span>
                        ) : null}
                      </>
                    ) : null}
                  </p>
                </>
              )}
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
          </CollapsibleDashboardSection>
        );

      case "advance-training":
        if (!tc) return null;
        return (
          <CollapsibleDashboardSection
            panelKey={`${domain}:advance-training`}
            title="Advance Training Cycle"
            className="card wide"
          >
            <p className="small muted" style={{ marginTop: 0 }}>
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

            <div className="advance-gates-panel card-inner-muted mt">
              <h4 className="small muted" style={{ margin: "0 0 0.5rem" }}>
                Advance gates (operator)
              </h4>
              <ul className="small mono validate-list" style={{ marginBottom: "0.65rem" }}>
                <li>
                  <span className="muted">can_advance:</span>{" "}
                  <strong>{tc.can_advance ? "true" : "false"}</strong>
                </li>
                <li>
                  <span className="muted">admin approved (full):</span>{" "}
                  <strong>{fullAdminOk ? "true" : "false"}</strong>
                </li>
                <li>
                  <span className="muted">advancing:</span>{" "}
                  <strong>{advancing ? "true" : "false"}</strong>
                </li>
              </ul>

              <div className="advance-disable-explain">
                <p className="small mono" style={{ margin: "0 0 0.35rem" }}>
                  <strong className="muted">Smoke</strong>{" "}
                  {advancing || !tc.can_advance ? (
                    <span className="muted">— disabled</span>
                  ) : (
                    <span className="ok">— enabled</span>
                  )}
                </p>
                {advancing || !tc.can_advance ? (
                  <ul className="small mono validate-list advance-reason-list">
                    {advancing ? (
                      <li>advancing request in flight</li>
                    ) : null}
                    {!tc.can_advance ? (
                      <li>
                        can_advance=false
                        {tc.advance_disabled_reason != null &&
                        String(tc.advance_disabled_reason).length > 0
                          ? `: ${tc.advance_disabled_reason}`
                          : ": (no reason code)"}
                      </li>
                    ) : null}
                  </ul>
                ) : null}

                <p className="small mono" style={{ margin: "0.55rem 0 0.35rem" }}>
                  <strong className="muted">Full</strong>{" "}
                  {advancing || !tc.can_advance || !fullAdminOk ? (
                    <span className="muted">— disabled</span>
                  ) : (
                    <span className="ok">— enabled</span>
                  )}
                </p>
                {advancing || !tc.can_advance || !fullAdminOk ? (
                  <ul className="small mono validate-list advance-reason-list">
                    {!fullAdminOk ? <li>admin approval unchecked</li> : null}
                    {advancing ? (
                      <li>advancing request in flight</li>
                    ) : null}
                    {!tc.can_advance ? (
                      <li>
                        can_advance=false
                        {tc.advance_disabled_reason != null &&
                        String(tc.advance_disabled_reason).length > 0
                          ? `: ${tc.advance_disabled_reason}`
                          : ": (no reason code)"}
                      </li>
                    ) : null}
                  </ul>
                ) : null}
              </div>
            </div>

            <div className="row-actions mt" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
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
          </CollapsibleDashboardSection>
        );

      case "staging":
        if (!st?.staging_path) return null;
        return (
          <CollapsibleDashboardSection panelKey={`${domain}:staging`} title="Staging" className="card">
            <p className="mono small" style={{ marginTop: 0 }}>
              {String(st.staging_path)}
            </p>
            <p className="small muted">
              Dataset ok: {String(st.dataset_ok)} · Train ok: {String(st.train_ok)}
            </p>
          </CollapsibleDashboardSection>
        );

      default:
        return null;
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">Dashboard</h2>
      <p className="small muted" style={{ marginTop: "-0.5rem", marginBottom: "0.75rem" }}>
        Drag ⠿ on each section to reorder. Layout is saved per domain in this browser.
      </p>
      {dashboardErr && <p className="err">{dashboardErr}</p>}

      {execId &&
      dashboard?.dashboard_status_label === "TRAINING" &&
      dashboard.training_telemetry ? (
        <section className="training-steps-hero" aria-label="Trainer step counter">
          <h3 className="training-steps-hero-title">Trainer steps</h3>
          <TrainingStepsHero tt={dashboard.training_telemetry} />
        </section>
      ) : null}

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={onDragEnd}
      >
        <SortableContext items={orderedBlockIds} strategy={verticalListSortingStrategy}>
          <div className="dashboard-sortable-list">
            {orderedBlockIds.map((blockId) => {
              const content = renderBlock(blockId);
              if (content == null) return null;
              return (
                <SortableDashboardBlock key={blockId} id={blockId}>
                  {content}
                </SortableDashboardBlock>
              );
            })}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
