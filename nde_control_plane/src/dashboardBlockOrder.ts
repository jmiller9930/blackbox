import type { ActiveJobPayload, DashboardPayload, TrainingCyclePayload } from "./context/StudioContext";

/** All dashboard blocks that can appear (subset shown based on data). */
export const DASHBOARD_BLOCK_ORDER_DEFAULT = [
  "system-status",
  "training-telemetry",
  "certified-summary",
  "job-in-progress",
  "pipeline-detail",
  "prior-baseline",
  "summary-grid",
  "advance-training",
  "staging",
] as const;

export type DashboardBlockId = (typeof DASHBOARD_BLOCK_ORDER_DEFAULT)[number];

const STORAGE_PREFIX = "nde-studio.dashboardBlockOrder.v1:";

function storageKey(domain: string): string {
  return `${STORAGE_PREFIX}${domain}`;
}

export function loadDashboardBlockOrder(domain: string): string[] {
  try {
    const raw = localStorage.getItem(storageKey(domain));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const allowed = new Set<string>(DASHBOARD_BLOCK_ORDER_DEFAULT);
    return parsed.filter((x): x is string => typeof x === "string" && allowed.has(x));
  } catch {
    return [];
  }
}

export function saveDashboardBlockOrder(domain: string, order: string[]): void {
  try {
    localStorage.setItem(storageKey(domain), JSON.stringify(order));
  } catch {
    /* ignore quota / private mode */
  }
}

/** Which blocks exist right now (visibility). Order follows default list. */
export function getVisibleDashboardBlockIds(args: {
  dashboard: DashboardPayload | null;
  execId: string | null;
  aj: ActiveJobPayload | null | undefined;
  featuredId: string | null;
  tc: TrainingCyclePayload | undefined;
  st: Record<string, unknown> | undefined;
}): DashboardBlockId[] {
  const { dashboard, execId, aj, featuredId, tc, st } = args;
  const vis = new Set<DashboardBlockId>();

  vis.add("system-status");

  if (
    dashboard?.training_telemetry &&
    execId &&
    dashboard.dashboard_status_label === "TRAINING"
  ) {
    vis.add("training-telemetry");
  }

  if (dashboard?.certified_feature_summary) vis.add("certified-summary");
  if (execId && aj) vis.add("job-in-progress");
  if (
    featuredId &&
    dashboard &&
    (dashboard.pipeline_steps?.length ?? 0) > 0
  ) {
    vis.add("pipeline-detail");
  }
  if (
    dashboard?.primary_run_is_cycle_candidate &&
    (dashboard.prior_certified_run_id || dashboard.prior_certified_version)
  ) {
    vis.add("prior-baseline");
  }

  vis.add("summary-grid");

  if (tc) vis.add("advance-training");
  if (st?.staging_path) vis.add("staging");

  return DASHBOARD_BLOCK_ORDER_DEFAULT.filter((id) => vis.has(id));
}

/**
 * Apply saved order; drop unknown/invisible ids; append newly visible ids in default order.
 */
export function mergeVisibleBlockOrder(
  saved: string[],
  visibleIds: DashboardBlockId[],
  defaultOrder: readonly DashboardBlockId[]
): DashboardBlockId[] {
  const visible = new Set(visibleIds);
  const seen = new Set<DashboardBlockId>();
  const out: DashboardBlockId[] = [];

  for (const id of saved) {
    if (!visible.has(id as DashboardBlockId)) continue;
    const bid = id as DashboardBlockId;
    if (seen.has(bid)) continue;
    out.push(bid);
    seen.add(bid);
  }
  for (const id of defaultOrder) {
    if (!visible.has(id) || seen.has(id)) continue;
    out.push(id);
    seen.add(id);
  }
  return out;
}
