import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type LegacyFinquantPayload = {
  active_run_label: string;
  finquant_status: "complete" | "training" | "failed" | "no_runs";
  legacy_progress_percent: number;
  progress_label: string | null;
  current_step: string | null;
  legacy_log_tail: string;
  finquant_legacy_root: string;
  paths_checked: Record<string, string>;
  adapters_hint?: { path: string; count: number; sample: string[] } | null;
  log_mtime_full_train?: string | null;
};

export type FinquantV02Dashboard = {
  state_path: string;
  train_complete: boolean;
  eval_passed: boolean;
  certified: boolean;
  score_label: string | null;
  eval_report_path: string | null;
  adapter_path: string | null;
  validated_at: string | null;
  last_error: string | null;
};

export type TrainingCycleBlocking = {
  run_id: string;
  reason: string;
  detail?: string;
};

export type ActiveCycleSnapshot = {
  run_id: string;
  progress_percent: number;
  current_step: string;
  pipeline_status: string;
  eval_passed: boolean | null;
  final_exam_passed: boolean | null;
  certified: boolean | null;
  last_error: string | null;
  version: string | null;
  log_tail: string;
};

export type ActiveJobPayload = {
  run_id: string;
  status: string;
  progress_percent: number;
  progress_label: string | null;
  current_node: string;
  latest_error: string | null;
  started_at: string | null;
  last_updated: string | null;
  elapsed_display: string;
  elapsed_ms: number;
  derived_started_from_folder?: boolean;
};

export type SystemPosture = "NO_ACTIVE_JOB" | "RUNNING" | "BLOCKED" | "FAILED";

export type CertifiedFeatureSummary = {
  run_id: string;
  status: string;
  completed_at: string | null;
  duration_display: string;
};

export type RunListRow = {
  run_id: string;
  path?: string;
  studio_status: string;
  progress_percent?: number | null;
};

export type PipelineStepRow = {
  index: number;
  name: string;
  graph_node: string;
  status: string;
  duration_ms: number | null;
  error: string | null;
};

export type ActionableErrorPayload = {
  problem: string;
  expected: string | null;
  fix: string;
  next_action: string;
};

export type CurrentNodeArtifacts = {
  graph_node: string;
  inputs: string[];
  outputs: string[];
};

export type TrainingCyclePayload = {
  latest_certified_version: string | null;
  latest_certified_run_id: string | null;
  next_candidate_version: string | null;
  next_run_id_would_be: string | null;
  active_run_id: string | null;
  blocking_run_id: string | null;
  active_blocking_candidate: TrainingCycleBlocking | null;
  active_cycle: ActiveCycleSnapshot | null;
  can_advance: boolean;
  advance_disabled_reason: string | null;
  graph_entrypoint: string;
  default_mode: string;
  full_training_requires_admin_approved: boolean;
};

export type DashboardPayload = {
  domain: string;
  active_run_id: string | null;
  /** Primary run shown for pipeline detail / context (may be certified while idle). */
  featured_run_id?: string | null;
  /** Tier-1 LangGraph cycle actually executing; null when idle. */
  execution_active_run_id?: string | null;
  system_posture?: SystemPosture;
  latest_certified_run_id?: string | null;
  system_status_lines?: string[];
  certified_feature_summary?: CertifiedFeatureSummary | null;
  primary_run_is_cycle_candidate?: boolean;
  prior_certified_run_id?: string | null;
  prior_certified_version?: string | null;
  progress_percent: number;
  /** FinQuant v0.2 step label e.g. 2726/3000 — present when legacy logs parsed */
  progress_label?: string | null;
  current_status: string;
  dashboard_status_label?: string | null;
  latest_error: string | null;
  active_job?: ActiveJobPayload | null;
  certification_status: string;
  certificate_on_disk: boolean;
  state_snapshot: Record<string, unknown> | null;
  staging_path_hint: string | null;
  training_log_tail: string;
  legacy_finquant?: LegacyFinquantPayload;
  finquant_legacy_training?: boolean;
  finquant_legacy_complete?: boolean;
  finquant_v02?: FinquantV02Dashboard | null;
  training_cycle?: TrainingCyclePayload;
  pipeline_steps?: PipelineStepRow[];
  current_step_index?: number;
  total_steps?: number;
  version_flow?: string | null;
  actionable_error?: ActionableErrorPayload | null;
  pipeline_focus_label?: string | null;
  pipeline_timeline_lines?: string[];
  pipeline_timing_lines?: string[];
  current_node_artifacts?: CurrentNodeArtifacts | null;
};

type StudioCtx = {
  domains: string[];
  domain: string;
  setDomain: (d: string) => void;
  runs: RunListRow[];
  selectedRunId: string | null;
  setSelectedRunId: (id: string | null) => void;
  dashboard: DashboardPayload | null;
  dashboardErr: string | null;
  refresh: () => Promise<void>;
  polling: boolean;
};

const Ctx = createContext<StudioCtx | null>(null);

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

export function StudioProvider({ children }: { children: ReactNode }) {
  const [domains, setDomains] = useState<string[]>(["secops", "finquant"]);
  const [domain, setDomain] = useState("secops");
  const [runs, setRuns] = useState<RunListRow[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [dashboardErr, setDashboardErr] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  const refresh = useCallback(async () => {
    setPolling(true);
    try {
      const domRes = await getJson<{ domains?: string[] }>("/api/domains");
      if (domRes.domains?.length) {
        setDomains(domRes.domains);
        setDomain((cur) =>
          domRes.domains!.includes(cur) ? cur : domRes.domains![0]
        );
      }

      const dEnc = encodeURIComponent(domain);
      const [dash, runList] = await Promise.all([
        getJson<DashboardPayload>(`/api/dashboard/${dEnc}`),
        getJson<{ runs?: RunListRow[] }>(`/api/runs/${dEnc}`),
      ]);

      setDashboard(dash);
      setDashboardErr(null);

      const rows = runList.runs ?? [];
      setRuns(rows);
      const ids = rows.map((r) => r.run_id);

      const lf = dash.legacy_finquant;
      const legacyLabel = lf?.active_run_label;
      const featured =
        dash.featured_run_id ?? dash.active_run_id;
      const preferred =
        featured &&
        (ids.includes(featured) ||
          (legacyLabel && featured === legacyLabel))
          ? featured
          : ids[0] ?? legacyLabel ?? null;

      setSelectedRunId((cur) => {
        if (
          cur &&
          (ids.includes(cur) || (legacyLabel && cur === legacyLabel))
        ) {
          return cur;
        }
        return preferred;
      });
    } catch (e) {
      setDashboardErr(String(e));
    } finally {
      setPolling(false);
    }
  }, [domain]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const t = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(t);
  }, [refresh]);

  const value = useMemo(
    () => ({
      domains,
      domain,
      setDomain,
      runs,
      selectedRunId,
      setSelectedRunId,
      dashboard,
      dashboardErr,
      refresh,
      polling,
    }),
    [
      domains,
      domain,
      runs,
      selectedRunId,
      dashboard,
      dashboardErr,
      refresh,
      polling,
    ]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStudio() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useStudio outside StudioProvider");
  return v;
}
