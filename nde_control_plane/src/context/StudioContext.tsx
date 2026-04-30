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

export type TrainingCyclePayload = {
  latest_certified_version: string | null;
  latest_certified_run_id: string | null;
  next_candidate_version: string | null;
  next_run_id_would_be: string | null;
  blocking_run_id: string | null;
  active_blocking_candidate: TrainingCycleBlocking | null;
  can_advance: boolean;
  advance_disabled_reason: string | null;
  graph_entrypoint: string;
  default_mode: string;
  full_training_requires_admin_approved: boolean;
};

export type DashboardPayload = {
  domain: string;
  active_run_id: string | null;
  progress_percent: number;
  /** FinQuant v0.2 step label e.g. 2726/3000 — present when legacy logs parsed */
  progress_label?: string | null;
  current_status: string;
  latest_error: string | null;
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
};

type StudioCtx = {
  domains: string[];
  domain: string;
  setDomain: (d: string) => void;
  runs: string[];
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
  const [runs, setRuns] = useState<string[]>([]);
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
        getJson<{ runs?: { run_id: string }[] }>(`/api/runs/${dEnc}`),
      ]);

      setDashboard(dash);
      setDashboardErr(null);

      const ids = (runList.runs ?? []).map((r) => r.run_id);
      setRuns(ids);

      const lf = dash.legacy_finquant;
      const legacyLabel = lf?.active_run_label;
      const preferred =
        dash.active_run_id &&
        (ids.includes(dash.active_run_id) ||
          (legacyLabel && dash.active_run_id === legacyLabel))
          ? dash.active_run_id
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
    const t = window.setInterval(() => void refresh(), 2500);
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
