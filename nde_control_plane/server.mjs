/**
 * NDE Studio — API backed by /data/NDE filesystem (+ optional /repo).
 */
import express from "express";
import fs from "fs";
import multer from "multer";
import path from "path";
import { execFile, spawn } from "child_process";
import { promisify } from "util";
import { fileURLToPath } from "url";

const execFileAsync = promisify(execFile);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3999);
const DATA_NDE = process.env.NDE_DATA_ROOT || "/data/NDE";
const REPO = process.env.REPO_MOUNT || "/repo";
/** Legacy FinQuant tree (host: /data/finquant-1) — not migrated into /data/NDE yet */
const FINQUANT_LEGACY_ROOT =
  process.env.FINQUANT_LEGACY_ROOT || "/data/finquant-1";
const LEGACY_FINQUANT_RUN_LABEL = "finquant-v0.2-full";
const FINQUANT_V02_ADAPTER_NAME = "finquant-1-qwen7b-v0.2";

const NODE_SEQUENCE = [
  "contract_ok",
  "dataset_ok",
  "train_ok",
  "eval_passed",
  "gate_passed",
  "final_exam_passed",
  "certified",
];

const ACCEPT_EXT = new Set([
  ".pdf",
  ".md",
  ".txt",
  ".json",
  ".xml",
  ".yaml",
  ".yml",
]);

const app = express();
app.use(express.json({ limit: "64mb" }));

function safeDomain(d) {
  if (!d || typeof d !== "string") return null;
  const t = d.replace(/[^a-z0-9_-]/gi, "");
  return t === d && d.length > 0 ? d : null;
}

function runRoot(domain, runId) {
  return path.join(DATA_NDE, domain, "runs", runId);
}

function readJsonSafe(p) {
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

function tailFile(p, maxBytes = 24000) {
  try {
    if (!fs.existsSync(p)) return "";
    const buf = fs.readFileSync(p);
    const s = buf.toString("utf8");
    return s.length > maxBytes ? s.slice(-maxBytes) : s;
  } catch {
    return "";
  }
}

/** Latest run dir by mtime of state.json or directory */
function listRunsSorted(domain) {
  const runsDir = path.join(DATA_NDE, domain, "runs");
  if (!fs.existsSync(runsDir)) return [];
  const entries = [];
  for (const name of fs.readdirSync(runsDir, { withFileTypes: true })) {
    if (!name.isDirectory()) continue;
    const rr = path.join(runsDir, name.name);
    const stPath = path.join(rr, "state.json");
    let mt = 0;
    try {
      mt = fs.existsSync(stPath)
        ? fs.statSync(stPath).mtimeMs
        : fs.statSync(rr).mtimeMs;
    } catch {
      mt = 0;
    }
    entries.push({ run_id: name.name, path: rr, mtime: mt });
  }
  entries.sort((a, b) => b.mtime - a.mtime);
  return entries;
}

/** LangGraph factory entrypoint on mounted NDE layout */
const RUN_GRAPH_SCRIPT = path.join(DATA_NDE, "tools", "run_graph.sh");

function parseSemverFromRunId(runId, domain) {
  if (!runId || !domain) return null;
  const esc = domain.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const anchored = new RegExp(`^${esc}-(v\\d+\\.\\d+)(?:-|$)`);
  const m1 = String(runId).match(anchored);
  if (m1) return m1[1];
  const m2 = String(runId).match(/(v\d+\.\d+)/);
  return m2 ? m2[1] : null;
}

function semverParts(ver) {
  const s = String(ver).replace(/^v/, "");
  return s.split(".").map((x) => parseInt(x, 10) || 0);
}

/** >0 if a > b */
function semverCompare(a, b) {
  const pa = semverParts(a);
  const pb = semverParts(b);
  const n = Math.max(pa.length, pb.length);
  for (let i = 0; i < n; i++) {
    const da = pa[i] || 0;
    const db = pb[i] || 0;
    if (da !== db) return da - db;
  }
  return 0;
}

function bumpMinorTrainingVersion(ver) {
  const p = semverParts(ver);
  const maj = p[0] ?? 0;
  const min = p[1] ?? 0;
  return `v${maj}.${min + 1}`;
}

/** Finished certified cycle (skip blocking on this folder). */
function isCycleCompleteCertified(domain, runId, state) {
  if (state?.certified === true) return true;
  return fs.existsSync(path.join(runRoot(domain, runId), "CERTIFICATE.json"));
}

function ndeDomainDirectoryExists(domain) {
  try {
    const p = path.join(DATA_NDE, domain);
    return fs.existsSync(p) && fs.statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function isTerminalCycleFailure(state) {
  if (!state || typeof state !== "object") return false;
  if (state.escalated) return true;
  const st = summarizeStatus(state);
  return (
    st === "final_exam_failed" ||
    st === "eval_failed" ||
    st === "train_failed" ||
    st === "dataset_failed" ||
    st === "contract_failed" ||
    st === "escalated"
  );
}

/**
 * Blocks advance if a LangGraph cycle run exists that is not certified and not in a terminal failure state,
 * if state.json is not yet written (graph in flight), or if escalation is active.
 */
function findBlockingCycleCandidate(domain) {
  const runsDir = path.join(DATA_NDE, domain, "runs");
  if (!fs.existsSync(runsDir)) return null;
  const names = fs
    .readdirSync(runsDir, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name);
  for (const name of names) {
    if (!name.includes("-cycle-")) continue;
    if (!name.startsWith(`${domain}-`)) continue;
    const stPath = path.join(runsDir, name, "state.json");
    if (!fs.existsSync(stPath)) {
      return {
        run_id: name,
        reason: "active_run_in_progress",
        detail: "No state.json yet — LangGraph run may be active",
      };
    }
    const st = readJsonSafe(stPath);
    if (st?.escalated === true) {
      return {
        run_id: name,
        reason: "active_run_in_progress",
        detail: String(st.escalate_reason || st.last_error || "escalated"),
      };
    }
    if (isCycleCompleteCertified(domain, name, st)) continue;
    if (isTerminalCycleFailure(st)) continue;
    return {
      run_id: name,
      reason: "active_run_in_progress",
      detail: summarizeStatus(st),
    };
  }
  return null;
}

function findLatestCertifiedTrainingVersion(domain) {
  let best = null;
  let bestVer = null;
  const sorted = listRunsSorted(domain);
  for (const { run_id } of sorted) {
    const stPath = path.join(runRoot(domain, run_id), "state.json");
    const st = readJsonSafe(stPath);
    if (st?.certified !== true) continue;
    let ver = parseSemverFromRunId(run_id, domain);
    if (!ver && st?.version) {
      const m = String(st.version).match(/v\d+\.\d+/);
      if (m) ver = m[0];
    }
    if (!ver) {
      const cert = readJsonSafe(path.join(runRoot(domain, run_id), "CERTIFICATE.json"));
      if (cert?.run_id) ver = parseSemverFromRunId(String(cert.run_id), domain);
    }
    if (!ver) continue;
    if (!bestVer || semverCompare(ver, bestVer) > 0) {
      bestVer = ver;
      best = { run_id, version: ver };
    }
  }
  if (domain === "finquant") {
    const legacyId = LEGACY_FINQUANT_RUN_LABEL;
    const lp = path.join(runRoot(domain, legacyId), "state.json");
    const lst = readJsonSafe(lp);
    if (lst?.certified === true) {
      const ver =
        lst.version && String(lst.version).match(/^v\d+\.\d+$/)
          ? String(lst.version)
          : "v0.2";
      if (!bestVer || semverCompare(ver, bestVer) > 0) {
        best = { run_id: legacyId, version: ver };
        bestVer = ver;
      }
    }
  }
  return best;
}

function allocateNextCycleRunId(domain, nextVer) {
  const runsDir = path.join(DATA_NDE, domain, "runs");
  fs.mkdirSync(runsDir, { recursive: true });
  let seq = 1;
  for (;;) {
    const rid = `${domain}-${nextVer}-cycle-${String(seq).padStart(3, "0")}`;
    if (!fs.existsSync(path.join(runsDir, rid))) return rid;
    seq++;
  }
}

const LANGGRAPH_NODE_ORDER = [
  "validate_domain_contract",
  "validate_training_dataset",
  "smoke_train",
  "smoke_eval",
  "evaluate_gate",
  "auto_reinforce",
  "retry_or_escalate",
  "final_exam",
  "certify",
];

function inferCurrentLangGraphStep(nodes) {
  let label = "starting";
  for (const name of LANGGRAPH_NODE_ORDER) {
    const row = nodes.find((n) => n.node === name);
    if (!row) continue;
    const st = row.status || "UNKNOWN";
    label = `${name} (${st})`;
    if (st === "failed" || st === "blocked") break;
  }
  return label;
}

function buildActiveCycleSnapshot(domain, runId) {
  const root = runRoot(domain, runId);
  const st = readJsonSafe(path.join(root, "state.json"));
  const pv = derivePipelineVisual(domain, runId);
  const nodes = listNodeStatuses(root);
  const step = pv
    ? `${pv.current_node} (${pv.dashboard_status})`
    : inferCurrentLangGraphStep(nodes);
  return {
    run_id: runId,
    progress_percent: pv?.progress_percent ?? progressPct(st),
    current_step: step,
    pipeline_status: pv?.pipeline_status ?? (st ? summarizeStatus(st) : "starting"),
    eval_passed: st?.eval_passed ?? null,
    final_exam_passed: st?.final_exam_passed ?? null,
    certified: st?.certified ?? null,
    last_error: pv?.latest_error ?? (st?.last_error != null ? String(st.last_error) : null),
    version: st?.version ?? null,
    log_tail: trainingLogTail(domain, runId),
  };
}

function buildTrainingCycleSummary(domain) {
  const certified = findLatestCertifiedTrainingVersion(domain);
  const blocking = findBlockingCycleCandidate(domain);
  const nextVer = certified ? bumpMinorTrainingVersion(certified.version) : null;
  const canAdvance = !!(certified && !blocking);
  const nextRunId =
    certified && nextVer && canAdvance ? allocateNextCycleRunId(domain, nextVer) : null;
  let advanceDisabledReason = null;
  if (!certified) advanceDisabledReason = "no_certified_version";
  else if (blocking) advanceDisabledReason = "active_run_in_progress";
  const activeRunId = blocking?.run_id ?? null;
  const active_cycle = activeRunId ? buildActiveCycleSnapshot(domain, activeRunId) : null;
  return {
    latest_certified_version: certified?.version ?? null,
    latest_certified_run_id: certified?.run_id ?? null,
    next_candidate_version: nextVer,
    next_run_id_would_be: nextRunId,
    active_run_id: activeRunId,
    blocking_run_id: activeRunId,
    active_blocking_candidate: blocking,
    active_cycle,
    can_advance: canAdvance,
    advance_disabled_reason: advanceDisabledReason,
    graph_entrypoint: RUN_GRAPH_SCRIPT,
    default_mode: "smoke",
    full_training_requires_admin_approved: true,
  };
}

function spawnLangGraphRun(domain, runId, mode, adminApproved) {
  const m = mode === "full" ? "full" : "smoke";
  const args = ["--domain", domain, "--mode", m, "--run-id", runId];
  if (m === "full") args.push("--require-approval");
  const rr = runRoot(domain, runId);
  fs.mkdirSync(rr, { recursive: true });
  if (m === "full" && adminApproved) {
    fs.writeFileSync(
      path.join(rr, "APPROVED"),
      `nde_studio_admin_approved_at=${new Date().toISOString()}\n`
    );
  }
  const env = {
    ...process.env,
    REPO_ROOT: process.env.REPO_ROOT || REPO,
    HOME: process.env.HOME || "/root",
    NDE_ROOT: DATA_NDE,
  };
  const child = spawn(RUN_GRAPH_SCRIPT, args, {
    env,
    detached: true,
    stdio: "ignore",
  });
  child.unref();
  return child;
}

/** Universal advance — POST /api/advance/:domain */
function performAdvanceTrainingCycle(rawDomain, body) {
  const domain = safeDomain(rawDomain);
  if (!domain) {
    return { status: 404, json: { ok: false, error: "domain_not_found" } };
  }
  if (!ndeDomainDirectoryExists(domain)) {
    return { status: 404, json: { ok: false, error: "domain_not_found" } };
  }

  const mode = body?.mode === "full" ? "full" : "smoke";
  if (mode === "full" && body?.admin_approved !== true) {
    return {
      status: 403,
      json: {
        ok: false,
        error: "admin_approval_required",
        message: "Full training requires admin_approved: true in JSON body",
      },
    };
  }

  if (!fs.existsSync(RUN_GRAPH_SCRIPT)) {
    return {
      status: 500,
      json: {
        ok: false,
        error: "internal_error",
        message: `run_graph_missing:${RUN_GRAPH_SCRIPT}`,
      },
    };
  }

  const spawnLock = path.join(DATA_NDE, domain, ".advance_spawning.lock");
  try {
    if (fs.existsSync(spawnLock)) {
      const ageMs = Date.now() - fs.statSync(spawnLock).mtimeMs;
      if (ageMs < 120000) {
        return {
          status: 409,
          json: {
            ok: false,
            error: "active_run_in_progress",
            detail: "advance_spawn_lock",
          },
        };
      }
      fs.unlinkSync(spawnLock);
    }
  } catch {
    /* ignore */
  }

  const certified = findLatestCertifiedTrainingVersion(domain);
  if (!certified) {
    return { status: 400, json: { ok: false, error: "no_certified_version" } };
  }

  const blocking = findBlockingCycleCandidate(domain);
  if (blocking) {
    return {
      status: 409,
      json: {
        ok: false,
        error: "active_run_in_progress",
        run_id: blocking.run_id,
        detail: blocking.detail,
      },
    };
  }

  const nextVer = bumpMinorTrainingVersion(certified.version);
  const runId = allocateNextCycleRunId(domain, nextVer);

  try {
    fs.writeFileSync(
      spawnLock,
      JSON.stringify({ run_id: runId, at: new Date().toISOString(), mode })
    );
    spawnLangGraphRun(domain, runId, mode, body?.admin_approved === true);
    try {
      fs.unlinkSync(spawnLock);
    } catch {
      /* ignore */
    }
    return {
      status: 200,
      json: {
        ok: true,
        domain,
        current_certified: certified.version,
        next_candidate: nextVer,
        run_id: runId,
      },
    };
  } catch (e) {
    try {
      fs.unlinkSync(spawnLock);
    } catch {
      /* ignore */
    }
    return {
      status: 500,
      json: {
        ok: false,
        error: "internal_error",
        message: String(e?.message || e),
      },
    };
  }
}

function progressPct(state) {
  if (!state || typeof state !== "object") return 0;
  let n = 0;
  for (const k of NODE_SEQUENCE) {
    if (state[k] === true) n++;
  }
  return Math.round((n / NODE_SEQUENCE.length) * 100);
}

function summarizeStatus(s) {
  if (s.escalated) return "escalated";
  if (s.certified) return "certified";
  if (s.final_exam_passed === false) return "final_exam_failed";
  if (s.eval_passed === false) return "eval_failed";
  if (s.train_ok === false) return "train_failed";
  if (s.dataset_ok === false) return "dataset_failed";
  if (s.contract_ok === false) return "contract_failed";
  return "in_progress_or_complete";
}

function listNodeStatuses(runPath) {
  const nodesDir = path.join(runPath, "nodes");
  if (!fs.existsSync(nodesDir)) return [];
  const out = [];
  for (const name of fs.readdirSync(nodesDir, { withFileTypes: true })) {
    if (!name.isDirectory()) continue;
    const np = path.join(nodesDir, name.name, "node_status.json");
    const j = readJsonSafe(np);
    if (j) {
      out.push({ node: name.name, ...j });
    } else {
      out.push({ node: name.name, status: "UNKNOWN" });
    }
  }
  return out.sort((a, b) => String(a.node).localeCompare(String(b.node)));
}

function trainingLogTail(domain, runId) {
  const rr = runRoot(domain, runId);
  const parts = [];
  for (const log of ["stdout.log", "stderr.log"]) {
    const p = path.join(rr, "nodes", "smoke_train", log);
    const t = tailFile(p, 32000);
    if (t) parts.push(`=== smoke_train/${log} ===\n${t}`);
  }
  return parts.join("\n\n").trim();
}

const FINQUANT_V02_STEPS = 3000;

function readUtf8Safe(p) {
  try {
    if (!fs.existsSync(p)) return "";
    return fs.readFileSync(p, "utf8");
  } catch {
    return "";
  }
}

/** Last window used for step regexes (last progress lines matter). */
function tailForParse(text) {
  if (!text) return "";
  return text.length > 4 * 1024 * 1024
    ? text.slice(-4 * 1024 * 1024)
    : text;
}

/** Prefer last `NNN/3000` — avoids unrelated trailing ratios (e.g. 1/5) wiping real progress. */
function parseLastThreeThousandStep(text) {
  const chunk = tailForParse(text);
  const re = /(\d+)\s*\/\s*3000\b/g;
  let m;
  let last = null;
  while ((m = re.exec(chunk)) !== null) {
    const cur = parseInt(m[1], 10);
    last = { cur, tot: FINQUANT_V02_STEPS };
  }
  return last;
}

/** Fallback: last N/N only when denominator is 3000 (same training scale). */
function parseLastProgressFraction(text) {
  if (!text) return null;
  const chunk = tailForParse(text);
  const re = /(\d+)\s*\/\s*(\d+)/g;
  let m;
  let last = null;
  while ((m = re.exec(chunk)) !== null) {
    const cur = parseInt(m[1], 10);
    const tot = parseInt(m[2], 10);
    if (tot === FINQUANT_V02_STEPS && cur >= 0) last = { cur, tot };
  }
  return last;
}

/** Last `NNN/TTT` in training logs for intra-stage progress (any denominator). */
function parseLastProgressFractionGeneric(text) {
  if (!text) return null;
  const chunk = tailForParse(text);
  const re = /(\d+)\s*\/\s*(\d+)/g;
  let m;
  let last = null;
  while ((m = re.exec(chunk)) !== null) {
    const cur = parseInt(m[1], 10);
    const tot = parseInt(m[2], 10);
    if (tot > 0 && cur >= 0 && tot < 1e9) last = { cur, tot };
  }
  return last;
}

function isCycleRunId(domain, runId) {
  if (!runId || !domain) return false;
  const rid = String(runId);
  return rid.startsWith(`${domain}-`) && rid.includes("-cycle-");
}

/** Primary dashboard focus: newest tier-1, else newest tier-2 cycle, else latest certified. */
function classifyPrimaryTier(domain, runId) {
  if (!isCycleRunId(domain, runId)) return null;
  const root = runRoot(domain, runId);
  const stPath = path.join(root, "state.json");
  const hasState = fs.existsSync(stPath);
  const st = hasState ? readJsonSafe(stPath) : null;
  if (!hasState) return 1;
  if (st?.certified === true || fs.existsSync(path.join(root, "CERTIFICATE.json"))) {
    return null;
  }
  if (st?.escalated === true || isTerminalCycleFailure(st)) return 2;
  return 1;
}

function resolveDashboardPrimaryRun(domain) {
  const sorted = listRunsSorted(domain);
  for (const row of sorted) {
    if (classifyPrimaryTier(domain, row.run_id) === 1) {
      return {
        run_id: row.run_id,
        state: readJsonSafe(path.join(row.path, "state.json")),
        is_cycle: true,
      };
    }
  }
  for (const row of sorted) {
    if (classifyPrimaryTier(domain, row.run_id) === 2) {
      return {
        run_id: row.run_id,
        state: readJsonSafe(path.join(row.path, "state.json")),
        is_cycle: true,
      };
    }
  }
  const cert = findLatestCertifiedTrainingVersion(domain);
  if (cert?.run_id) {
    const rp = runRoot(domain, cert.run_id);
    return {
      run_id: cert.run_id,
      state: readJsonSafe(path.join(rp, "state.json")),
      is_cycle: isCycleRunId(domain, cert.run_id),
    };
  }
  if (sorted[0]) {
    const rp = sorted[0].path;
    return {
      run_id: sorted[0].run_id,
      state: readJsonSafe(path.join(rp, "state.json")),
      is_cycle: isCycleRunId(domain, sorted[0].run_id),
    };
  }
  return { run_id: null, state: null, is_cycle: false };
}

function formatElapsed(ms) {
  const s = Math.floor(Math.max(0, ms) / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function deriveRunTimestamps(domain, runId, state, _nodes) {
  let started = state?.started_at ? String(state.started_at) : null;
  let updated = state?.updated_at ? String(state.updated_at) : null;
  const root = runRoot(domain, runId);
  let derivedStart = false;
  if (!started) {
    let minMs = null;
    const nodesDir = path.join(root, "nodes");
    try {
      if (fs.existsSync(nodesDir)) {
        for (const ent of fs.readdirSync(nodesDir, { withFileTypes: true })) {
          if (!ent.isDirectory()) continue;
          const np = path.join(nodesDir, ent.name, "node_status.json");
          if (fs.existsSync(np)) {
            const stt = fs.statSync(np);
            minMs = minMs === null ? stt.mtimeMs : Math.min(minMs, stt.mtimeMs);
          }
        }
      }
    } catch {
      /* ignore */
    }
    if (minMs !== null) {
      started = new Date(minMs).toISOString();
      derivedStart = true;
    } else {
      try {
        const sr = fs.statSync(root);
        const b = sr.birthtimeMs && sr.birthtimeMs > 0 ? sr.birthtimeMs : sr.mtimeMs;
        started = new Date(b).toISOString();
        derivedStart = true;
      } catch {
        started = null;
      }
    }
  }
  if (!updated) {
    const sp = path.join(root, "state.json");
    try {
      if (fs.existsSync(sp)) {
        updated = fs.statSync(sp).mtime.toISOString();
      } else {
        let maxMs = null;
        const nodesDir = path.join(root, "nodes");
        if (fs.existsSync(nodesDir)) {
          for (const ent of fs.readdirSync(nodesDir, { withFileTypes: true })) {
            if (!ent.isDirectory()) continue;
            const np = path.join(nodesDir, ent.name, "node_status.json");
            if (fs.existsSync(np)) {
              const stt = fs.statSync(np);
              maxMs = maxMs === null ? stt.mtimeMs : Math.max(maxMs, stt.mtimeMs);
            }
          }
        }
        updated =
          maxMs !== null
            ? new Date(maxMs).toISOString()
            : started || new Date().toISOString();
      }
    } catch {
      updated = started || new Date().toISOString();
    }
  }
  const startedMs = started ? Date.parse(started) : NaN;
  const now = Date.now();
  const elapsedMs = Number.isFinite(startedMs) ? Math.max(0, now - startedMs) : 0;
  return {
    started_at: started,
    last_updated: updated,
    elapsed_ms: elapsedMs,
    derived_started_from_folder: derivedStart,
  };
}

function nodeStatMap(nodes) {
  const m = {};
  for (const n of nodes || []) {
    m[String(n.node)] = String(n.status || "").toUpperCase();
  }
  return m;
}

/**
 * Progress, status, runtime for one run (dashboard + runs list).
 * Maps LangGraph stages to directive percentages; uses NNN/TTT inside smoke_train band.
 */
function derivePipelineVisual(domain, runId) {
  if (!runId) return null;
  const root = runRoot(domain, runId);
  const statePath = path.join(root, "state.json");
  const state = fs.existsSync(statePath) ? readJsonSafe(statePath) : null;
  const nodes = listNodeStatuses(root);
  const nm = nodeStatMap(nodes);
  const trainLog = trainingLogTail(domain, runId);
  const ts = deriveRunTimestamps(domain, runId, state, nodes);

  const npass = (name) => nm[name] === "PASS";
  const nfail = (name) =>
    nm[name] === "FAIL" || nm[name] === "BLOCKED" || nm[name] === "FAILED";

  function runListBadge(dashboardStatus) {
    if (
      dashboardStatus === "TRAINING" ||
      dashboardStatus === "EVAL" ||
      dashboardStatus === "STARTING" ||
      dashboardStatus === "RUNNING"
    ) {
      return "RUNNING";
    }
    if (dashboardStatus === "BLOCKED") return "BLOCKED";
    if (dashboardStatus === "FAILED") return "FAILED";
    if (dashboardStatus === "CERTIFIED") return "CERTIFIED";
    return "UNKNOWN";
  }

  function activeJobBase(
    progressPercent,
    dashboardStatus,
    pipelineStatus,
    currentNode,
    latestError,
    progressLabel
  ) {
    return {
      progress_percent: progressPercent,
      progress_label: progressLabel ?? null,
      pipeline_status: pipelineStatus,
      dashboard_status: dashboardStatus,
      current_node: currentNode,
      latest_error: latestError != null ? String(latestError) : null,
      active_job: {
        run_id: runId,
        status: dashboardStatus,
        progress_percent: progressPercent,
        progress_label: progressLabel ?? null,
        current_node: currentNode,
        latest_error: latestError != null ? String(latestError) : null,
        started_at: ts.started_at,
        last_updated: ts.last_updated,
        elapsed_display: formatElapsed(ts.elapsed_ms),
        elapsed_ms: ts.elapsed_ms,
        derived_started_from_folder: ts.derived_started_from_folder,
      },
      run_list_badge: runListBadge(dashboardStatus),
    };
  }

  const certOnDisk = fs.existsSync(path.join(root, "CERTIFICATE.json"));
  if (state?.certified === true || certOnDisk) {
    return activeJobBase(100, "CERTIFIED", "certified", "certify", null, null);
  }

  if (state?.escalated === true) {
    let pct = 10;
    if (state?.contract_ok === true) pct = Math.max(pct, 5);
    if (state?.dataset_ok === true) pct = Math.max(pct, 15);
    if (state?.train_ok === true) pct = Math.max(pct, 60);
    if (state?.eval_passed === true) pct = Math.max(pct, 75);
    if (state?.gate_passed === true) pct = Math.max(pct, 85);
    if (state?.final_exam_passed === true) pct = Math.max(pct, 95);
    return activeJobBase(
      Math.min(99, pct),
      "FAILED",
      "escalated",
      "retry_or_escalate",
      state?.escalate_reason || state?.last_error,
      null
    );
  }

  if (state && isTerminalCycleFailure(state)) {
    const sum = summarizeStatus(state);
    if (sum === "contract_failed" || state?.contract_ok === false) {
      return activeJobBase(
        5,
        "BLOCKED",
        "blocked",
        "validate_domain_contract",
        state?.last_error
          ? `BLOCKED: ${state.last_error}`
          : "BLOCKED: domain contract failed",
        null
      );
    }
    if (sum === "dataset_failed" || state?.dataset_ok === false) {
      return activeJobBase(
        15,
        "BLOCKED",
        "blocked",
        "validate_training_dataset",
        state?.last_error
          ? `BLOCKED: ${state.last_error}`
          : "BLOCKED: dataset validation failed",
        null
      );
    }
    if (sum === "train_failed" || state?.train_ok === false) {
      return activeJobBase(
        60,
        "FAILED",
        "failed",
        "smoke_train",
        state?.last_error,
        null
      );
    }
    if (sum === "eval_failed" || state?.eval_passed === false) {
      return activeJobBase(75, "FAILED", "failed", "smoke_eval", state?.last_error, null);
    }
    if (sum === "final_exam_failed" || state?.final_exam_passed === false) {
      return activeJobBase(
        95,
        "FAILED",
        "failed",
        "final_exam",
        state?.last_error,
        null
      );
    }
  }

  const cOk = state?.contract_ok === true || npass("validate_domain_contract");
  const cBad =
    state?.contract_ok === false ||
    nfail("validate_domain_contract") ||
    nm["validate_domain_contract"] === "FAIL";

  if (cBad) {
    return activeJobBase(
      5,
      "BLOCKED",
      "blocked",
      "validate_domain_contract",
      state?.last_error || "BLOCKED: domain contract failed",
      null
    );
  }

  if (!cOk && !state && nodes.length === 0) {
    return activeJobBase(
      2,
      "STARTING",
      "starting",
      "validate_domain_contract",
      null,
      null
    );
  }

  if (!cOk) {
    return activeJobBase(4, "RUNNING", "in_progress", "validate_domain_contract", null, null);
  }

  const dOk = state?.dataset_ok === true || npass("validate_training_dataset");
  const dBad =
    state?.dataset_ok === false ||
    nfail("validate_training_dataset") ||
    nm["validate_training_dataset"] === "FAIL";

  if (dBad) {
    return activeJobBase(
      15,
      "BLOCKED",
      "blocked",
      "validate_training_dataset",
      state?.last_error
        ? `BLOCKED: ${state.last_error}`
        : "BLOCKED: dataset validation failed",
      null
    );
  }

  if (!dOk) {
    return activeJobBase(
      12,
      "RUNNING",
      "in_progress",
      "validate_training_dataset",
      null,
      null
    );
  }

  const tOk = state?.train_ok === true || npass("smoke_train");
  const tBad =
    state?.train_ok === false ||
    nfail("smoke_train") ||
    nm["smoke_train"] === "SKIPPED";

  if (tBad) {
    return activeJobBase(
      60,
      "FAILED",
      "failed",
      "smoke_train",
      state?.last_error,
      null
    );
  }

  if (!tOk) {
    const frac = parseLastProgressFractionGeneric(trainLog);
    let p = 18;
    if (frac && frac.tot > 0) {
      p = 15 + Math.min(1, frac.cur / frac.tot) * 45;
    }
    const pl = frac && frac.tot > 0 ? `${frac.cur}/${frac.tot}` : null;
    return activeJobBase(Math.round(p), "TRAINING", "training", "smoke_train", null, pl);
  }

  const eOk = state?.eval_passed === true || npass("smoke_eval");
  const eBad = state?.eval_passed === false || nfail("smoke_eval");

  if (eBad) {
    return activeJobBase(75, "FAILED", "failed", "smoke_eval", state?.last_error, null);
  }

  if (!eOk) {
    return activeJobBase(72, "EVAL", "evaluating", "smoke_eval", null, null);
  }

  const gOk = state?.gate_passed === true || npass("evaluate_gate");
  const gBad = state?.gate_passed === false || nfail("evaluate_gate");

  if (gBad) {
    return activeJobBase(85, "FAILED", "failed", "evaluate_gate", state?.last_error, null);
  }

  if (!gOk) {
    return activeJobBase(80, "EVAL", "evaluating", "evaluate_gate", null, null);
  }

  const feOk = state?.final_exam_passed === true || npass("final_exam");
  const feBad = state?.final_exam_passed === false || nfail("final_exam");

  if (feBad) {
    return activeJobBase(95, "FAILED", "failed", "final_exam", state?.last_error, null);
  }

  if (!feOk) {
    return activeJobBase(90, "EVAL", "evaluating", "final_exam", null, null);
  }

  const cyOk = npass("certify");
  if (!cyOk) {
    return activeJobBase(97, "RUNNING", "in_progress", "certify", null, null);
  }

  return activeJobBase(100, "CERTIFIED", "certified", "certify", null, null);
}

/** Operator-facing 7-step pipeline (smoke_eval shown as run_eval). */
const PIPELINE_OPERATOR_STEPS = [
  { index: 1, graph_node: "validate_domain_contract", name: "validate_domain_contract" },
  { index: 2, graph_node: "validate_training_dataset", name: "validate_training_dataset" },
  { index: 3, graph_node: "smoke_train", name: "smoke_train" },
  { index: 4, graph_node: "smoke_eval", name: "run_eval" },
  { index: 5, graph_node: "evaluate_gate", name: "evaluate_gate" },
  { index: 6, graph_node: "final_exam", name: "final_exam" },
  { index: 7, graph_node: "certify", name: "certify" },
];

function proofEndMs(npPath, j) {
  if (j?.updated_at) {
    const t = Date.parse(String(j.updated_at));
    if (Number.isFinite(t)) return t;
  }
  try {
    return fs.statSync(npPath).mtimeMs;
  } catch {
    return null;
  }
}

function extractStagingHintFromTrainingYaml(domain) {
  const configPath = path.join(DATA_NDE, domain, "training", "config.yaml");
  if (!fs.existsSync(configPath)) {
    return { config_path: configPath, resolved_hint: null, file_exists: false };
  }
  const txt = readUtf8Safe(configPath).slice(0, 48000);
  let resolved = null;
  for (const line of txt.split("\n")) {
    const md = line.match(/^\s*dataset\s*:\s*["']?([^"'\n#]+)/i);
    if (md) {
      resolved = md[1].trim().replace(/["']\s*$/, "");
      break;
    }
  }
  if (!resolved) {
    for (const line of txt.split("\n")) {
      const m = line.match(
        /^\s*(staging[_a-z]*path|dataset[_a-z]*path|train[_a-z]*file|jsonl[_a-z]*path)\s*:\s*["']?([^"'\n#]+)/i
      );
      if (m) {
        resolved = m[2].trim().replace(/["']\s*$/, "");
        break;
      }
    }
  }
  if (!resolved) {
    const m2 = txt.match(/[/][^\s"']+\.jsonl\b/);
    if (m2) resolved = m2[0];
  }
  return { config_path: configPath, resolved_hint: resolved, file_exists: true };
}

function buildVersionFlowString(domain, runId, primaryIsCycle, tcSummary, primaryState, pv) {
  const priorV = tcSummary?.latest_certified_version || "—";
  const candV =
    (primaryState?.version && String(primaryState.version)) ||
    parseSemverFromRunId(runId, domain) ||
    "—";
  const tailRaw = pv?.dashboard_status || "IN_PROGRESS";
  const tail =
    tailRaw === "CERTIFIED"
      ? "CERTIFIED"
      : tailRaw === "BLOCKED"
        ? "BLOCKED"
        : tailRaw === "FAILED"
          ? "FAILED"
          : tailRaw === "TRAINING" || tailRaw === "EVAL" || tailRaw === "RUNNING" || tailRaw === "STARTING"
            ? "RUNNING"
            : String(tailRaw).toUpperCase();
  if (!primaryIsCycle && pv?.dashboard_status === "CERTIFIED") {
    return `${priorV} certified`;
  }
  return `${priorV} certified → ${candV} candidate → ${tail}`;
}

function buildActionableErrorBlock(domain, rawErr, primaryState, stagingHint) {
  const stripped = String(rawErr || "")
    .replace(/^BLOCKED:\s*/i, "")
    .trim();
  const blob = `${stripped} ${primaryState?.last_error || ""}`.toLowerCase();
  const looksStaging =
    /jsonl|staging|dataset/.test(blob) &&
    /not found|missing|fail|unavailable|dataset_ok/.test(blob);
  if (looksStaging) {
    const expected =
      stagingHint?.resolved_hint ||
      primaryState?.staging_path ||
      primaryState?.artifacts?.staging_path ||
      (stagingHint?.file_exists
        ? `(configure path in ${stagingHint.config_path})`
        : `(create ${stagingHint?.config_path || path.join(DATA_NDE, domain, "training", "config.yaml")})`);
    return {
      problem: "Staging training dataset is missing.",
      expected: String(expected),
      fix: "Upload/source material, run Process Sources, or correct training/config.yaml dataset path.",
      next_action: "Fix dataset, then retry Advance Training Cycle.",
    };
  }
  return {
    problem: stripped || "Pipeline stopped.",
    expected:
      stagingHint?.config_path && stagingHint.file_exists
        ? `Review dataset paths in ${stagingHint.config_path}`
        : null,
    fix: "Inspect node proofs under this run’s nodes/ directory and correct configuration or inputs.",
    next_action: "Resolve the issue, then run Advance Training Cycle again if appropriate.",
  };
}

function buildCurrentNodeArtifacts(domain, runId, graphNode, primaryState, stagingHint) {
  const rr = runRoot(domain, runId);
  const domCfg = path.join(DATA_NDE, domain, "domain_config.yaml");
  const trainCfg = path.join(DATA_NDE, domain, "training", "config.yaml");
  const inputs = [
    `domain_config.yaml → ${domCfg}`,
    `training/config.yaml → ${trainCfg}`,
  ];
  const staging =
    stagingHint?.resolved_hint ||
    primaryState?.staging_path ||
    primaryState?.artifacts?.staging_path ||
    `(expected staging JSONL from training/config.yaml — ${trainCfg})`;
  inputs.push(`expected staging dataset → ${staging}`);
  const outputs = [
    `node_status.json → ${path.join(rr, "nodes", graphNode, "node_status.json")}`,
    `state.json → ${path.join(rr, "state.json")}`,
  ];
  return { graph_node: graphNode, inputs, outputs };
}

function buildPipelineDashboardFields(
  domain,
  runId,
  primaryState,
  pv,
  tcSummary,
  primaryIsCycle,
  certificateOnDisk,
  stagingHint
) {
  const total_steps = PIPELINE_OPERATOR_STEPS.length;
  const root = runRoot(domain, runId);
  const ts = deriveRunTimestamps(domain, runId, primaryState, []);
  const runStartMs = ts.started_at ? Date.parse(ts.started_at) : null;

  const rowMeta = [];
  let prevEndMs = Number.isFinite(runStartMs) ? runStartMs : null;

  for (const def of PIPELINE_OPERATOR_STEPS) {
    const np = path.join(root, "nodes", def.graph_node, "node_status.json");
    const j = readJsonSafe(np);
    let status = null;
    let duration_ms = null;
    let error = null;

    if (j && j.status) {
      const raw = String(j.status).toUpperCase();
      if (raw === "PASS" || raw === "OK" || raw === "PASSED") status = "PASS";
      else if (raw === "SKIPPED") status = "SKIPPED";
      else status = "FAIL";
      if (status === "FAIL" || status === "SKIPPED") {
        error =
          (j.failure_reason && String(j.failure_reason)) ||
          (Array.isArray(j.errors) && j.errors.length ? j.errors.map(String).join("; ") : null) ||
          (primaryState?.last_error != null ? String(primaryState.last_error) : null);
      }
      const endMs = proofEndMs(np, j);
      if (prevEndMs != null && endMs != null) {
        duration_ms = Math.max(0, endMs - prevEndMs);
      }
      if (endMs != null) prevEndMs = endMs;
    }
    rowMeta.push({ def, j, np, status, duration_ms, error });
  }

  const ixFail = rowMeta.findIndex((r) => r.status === "FAIL");
  const ixSkip = rowMeta.findIndex((r) => r.status === "SKIPPED");

  if (ixFail >= 0) {
    for (let k = ixFail + 1; k < rowMeta.length; k++) {
      if (rowMeta[k].status === null) rowMeta[k].status = "PENDING";
    }
  } else if (ixSkip >= 0) {
    for (let k = ixSkip + 1; k < rowMeta.length; k++) {
      if (rowMeta[k].status === null) rowMeta[k].status = "PENDING";
    }
  } else {
    const ixNull = rowMeta.findIndex((r) => r.status === null);
    if (ixNull >= 0) {
      rowMeta[ixNull].status = "RUNNING";
      for (let k = ixNull + 1; k < rowMeta.length; k++) {
        if (rowMeta[k].status === null) rowMeta[k].status = "PENDING";
      }
    }
  }

  if (
    (primaryState?.certified === true || certificateOnDisk) &&
    !rowMeta.some((r) => r.status === "FAIL")
  ) {
    for (const r of rowMeta) {
      if (r.status === null || r.status === "RUNNING" || r.status === "PENDING") {
        r.status = "PASS";
      }
    }
  }

  const pipeline_steps = rowMeta.map((r) => ({
    index: r.def.index,
    name: r.def.name,
    graph_node: r.def.graph_node,
    status: r.status || "PENDING",
    duration_ms: r.duration_ms,
    error: r.error,
  }));

  const nonPass = pipeline_steps.find((s) => s.status !== "PASS");
  let current_step_index = nonPass ? nonPass.index : total_steps;
  const focusDef = PIPELINE_OPERATOR_STEPS.find((d) => d.index === current_step_index);
  const pipeline_focus_label = focusDef
    ? `Step ${current_step_index} / ${total_steps} — ${focusDef.name}`
    : `Step ${total_steps} / ${total_steps} — certify`;

  const timeline_lines = pipeline_steps.map((s) => `${s.status} ${s.name}`);
  const timing_lines = [];
  for (const r of rowMeta) {
    const ms = r.duration_ms;
    const nm = r.def.name;
    if (r.status === "PASS" && ms != null) {
      timing_lines.push(`${nm}: completed in ${Math.round(ms / 1000)}s`);
    } else if (r.status === "FAIL" && ms != null) {
      timing_lines.push(`${nm}: failed after ${Math.round(ms / 1000)}s`);
    } else if (r.status === "FAIL" && ms == null) {
      timing_lines.push(`${nm}: failed`);
    }
  }

  const version_flow = buildVersionFlowString(
    domain,
    runId,
    primaryIsCycle,
    tcSummary,
    primaryState,
    pv
  );

  const latestErr = pv?.latest_error ?? primaryState?.last_error ?? null;
  const needsGuidance =
    !!String(latestErr || "").trim() ||
    pv?.dashboard_status === "BLOCKED" ||
    pv?.dashboard_status === "FAILED";
  const actionable_error = needsGuidance
    ? buildActionableErrorBlock(domain, latestErr || "", primaryState, stagingHint)
    : null;

  const focusGraph = focusDef?.graph_node || pv?.current_node || "validate_domain_contract";
  const current_node_artifacts = buildCurrentNodeArtifacts(
    domain,
    runId,
    focusGraph,
    primaryState,
    stagingHint
  );

  return {
    pipeline_steps,
    current_step_index,
    total_steps,
    version_flow,
    actionable_error,
    pipeline_focus_label,
    pipeline_timeline_lines: timeline_lines,
    pipeline_timing_lines: timing_lines,
    current_node_artifacts,
  };
}

function emptyPipelineDashboardFields() {
  return {
    pipeline_steps: [],
    current_step_index: 0,
    total_steps: 7,
    version_flow: null,
    actionable_error: null,
    pipeline_focus_label: null,
    pipeline_timeline_lines: [],
    pipeline_timing_lines: [],
    current_node_artifacts: null,
  };
}

function runStatusSortRank(badge) {
  if (badge === "RUNNING") return 0;
  if (badge === "BLOCKED") return 1;
  if (badge === "FAILED") return 2;
  if (badge === "CERTIFIED") return 3;
  return 4;
}

function legacyTrainingComplete(parseBlob, step3000) {
  if (!parseBlob) return false;
  if (/\btrain_runtime\b/i.test(parseBlob)) return true;
  if (/\b3000\s*\/\s*3000\b/.test(parseBlob)) return true;
  if (
    step3000 &&
    step3000.tot === FINQUANT_V02_STEPS &&
    step3000.cur >= FINQUANT_V02_STEPS
  ) {
    return true;
  }
  return false;
}

function legacyTrainingFailed(parseBlob, complete) {
  if (complete || !parseBlob) return false;
  const tail =
    parseBlob.length > 200000 ? parseBlob.slice(-200000) : parseBlob;
  return /traceback|out of memory|\boom\b|cuda.*out of memory|runtimeerror|segmentation fault|\bkilled\b|nan loss|error: exception|child process.*non-zero exit/i.test(
    tail
  );
}

function buildFinquantLegacySection() {
  const paths = {
    full_train_log: path.join(
      FINQUANT_LEGACY_ROOT,
      "reports",
      "v0.2_full_train.log"
    ),
    full_stdout_log: path.join(
      FINQUANT_LEGACY_ROOT,
      "reports",
      "full_train_stdout.log"
    ),
    adapters_dir: path.join(FINQUANT_LEGACY_ROOT, "adapters"),
  };

  const fullTrain = readUtf8Safe(paths.full_train_log);
  const fullOut = readUtf8Safe(paths.full_stdout_log);
  const parseBlob = [fullTrain, fullOut].filter(Boolean).join("\n");
  const hasAnyLogFile =
    fs.existsSync(paths.full_train_log) ||
    fs.existsSync(paths.full_stdout_log);

  let step3000 = parseLastThreeThousandStep(parseBlob);
  if (!step3000) step3000 = parseLastProgressFraction(parseBlob);

  const complete = legacyTrainingComplete(parseBlob, step3000);
  const failed = legacyTrainingFailed(parseBlob, complete);

  let legacy_progress_percent = 0;
  let progress_label = null;
  if (step3000 && step3000.tot > 0) {
    legacy_progress_percent = Math.min(
      100,
      Math.round((step3000.cur / step3000.tot) * 100)
    );
    progress_label = `${step3000.cur}/${step3000.tot}`;
  }
  if (complete) {
    legacy_progress_percent = 100;
    progress_label = `${FINQUANT_V02_STEPS}/${FINQUANT_V02_STEPS}`;
  }

  let finquant_status = "no_runs";
  if (!hasAnyLogFile && !parseBlob.trim()) {
    finquant_status = "no_runs";
  } else if (complete) {
    finquant_status = "complete";
  } else if (failed) {
    finquant_status = "failed";
  } else if (step3000 && step3000.cur < FINQUANT_V02_STEPS) {
    finquant_status = "training";
  } else if (parseBlob.trim()) {
    finquant_status = "no_runs";
  }

  const legacy_log_tail =
    tailFile(paths.full_train_log, 52000) ||
    tailFile(paths.full_stdout_log, 52000) ||
    "";

  let adapters_hint = null;
  try {
    if (fs.existsSync(paths.adapters_dir)) {
      const names = fs.readdirSync(paths.adapters_dir);
      adapters_hint = {
        path: paths.adapters_dir,
        count: names.length,
        sample: names.slice(0, 16),
      };
    }
  } catch {
    /* ignore */
  }

  return {
    active_run_label: LEGACY_FINQUANT_RUN_LABEL,
    finquant_status,
    legacy_progress_percent,
    progress_label,
    current_step: progress_label,
    legacy_log_tail,
    finquant_legacy_root: FINQUANT_LEGACY_ROOT,
    paths_checked: paths,
    adapters_hint,
    log_mtime_full_train: fs.existsSync(paths.full_train_log)
      ? fs.statSync(paths.full_train_log).mtime.toISOString()
      : null,
  };
}

function mergeFinquantDashboard(base, legacyFin) {
  if (base.primary_run_is_cycle_candidate) {
    return {
      ...base,
      legacy_finquant: legacyFin,
    };
  }

  const ss = base.state_snapshot;
  const v02 = ss && ss.version === "v0.2";

  const legacyHeader = legacyFin.legacy_log_tail
    ? `=== FinQuant v0.2 (${FINQUANT_LEGACY_ROOT}/reports) ===\n${legacyFin.legacy_log_tail}\n`
    : "";
  const out = {
    ...base,
    legacy_finquant: legacyFin,
    progress_label: base.progress_label ?? legacyFin.progress_label ?? null,
    training_log_tail: [legacyHeader, base.training_log_tail || ""]
      .filter(Boolean)
      .join("\n"),
  };

  if (v02 && ss.train_ok === true) {
    out.active_run_id = LEGACY_FINQUANT_RUN_LABEL;
    out.progress_percent = 100;
    out.progress_label = legacyFin.progress_label ?? "3000/3000";
    out.finquant_legacy_complete = true;
    out.finquant_legacy_training = false;
    if (ss.eval_passed === false) {
      out.current_status = "eval_failed";
    } else if (ss.certified === true) {
      out.current_status = "certified";
    } else {
      out.current_status = "complete";
    }
    return out;
  }
  if (v02 && ss.train_ok === false) {
    out.active_run_id = LEGACY_FINQUANT_RUN_LABEL;
    out.progress_percent = legacyFin.legacy_progress_percent ?? 0;
    out.current_status = "validation_failed";
    return out;
  }

  const fs = legacyFin.finquant_status;

  if (fs === "complete") {
    out.active_run_id = legacyFin.active_run_label;
    out.progress_percent = 100;
    out.current_status = "complete";
    out.finquant_legacy_complete = true;
    out.finquant_legacy_training = false;
    return out;
  }
  if (fs === "training") {
    out.active_run_id = legacyFin.active_run_label;
    out.progress_percent = legacyFin.legacy_progress_percent;
    out.current_status = "training";
    out.finquant_legacy_training = true;
    return out;
  }
  if (fs === "failed") {
    out.active_run_id = legacyFin.active_run_label;
    out.progress_percent = legacyFin.legacy_progress_percent;
    out.current_status = "failed";
    return out;
  }
  if (!base.latest_run_id) {
    out.active_run_id = null;
    out.current_status = "no_runs";
    out.progress_percent = 0;
  }
  return out;
}

function buildFinquantV02DashboardBlock(state) {
  if (!state || state.version !== "v0.2") return null;
  const casesPass = state.eval_summary?.cases_pass ?? null;
  const casesTotal = state.eval_summary?.cases_total ?? null;
  return {
    state_path: path.join(runRoot("finquant", LEGACY_FINQUANT_RUN_LABEL), "state.json"),
    train_complete: state.train_ok === true,
    eval_passed: state.eval_passed === true,
    certified: state.certified === true,
    score_label:
      casesPass != null && casesTotal != null
        ? `${casesPass} / ${casesTotal} cases`
        : null,
    eval_report_path: state.eval_report ?? null,
    adapter_path: state.adapter_path ?? null,
    validated_at: state.validated_at ?? null,
    last_error: state.last_error ?? null,
  };
}

function parseEvalFinquantStdout(stdout) {
  if (!stdout || typeof stdout !== "string") return null;
  const start = stdout.indexOf("{");
  if (start < 0) return null;
  let depth = 0;
  for (let i = start; i < stdout.length; i++) {
    const c = stdout[i];
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) {
        try {
          return JSON.parse(stdout.slice(start, i + 1));
        } catch {
          return null;
        }
      }
    }
  }
  return null;
}

function finquantV02Paths() {
  const adapterPath = path.join(
    FINQUANT_LEGACY_ROOT,
    "adapters",
    FINQUANT_V02_ADAPTER_NAME
  );
  const trainLog = path.join(FINQUANT_LEGACY_ROOT, "reports", "v0.2_full_train.log");
  const evalReport = path.join(FINQUANT_LEGACY_ROOT, "reports", "v0.2_eval_report.md");
  const runDir = path.join(runRoot("finquant", LEGACY_FINQUANT_RUN_LABEL));
  const statePath = path.join(runDir, "state.json");
  return { adapterPath, trainLog, evalReport, runDir, statePath };
}

/** Extra markdown/txt reports to scan for training proof (comma-separated env + defaults). */
function finquantV02OptionalReportPaths() {
  const out = [];
  const env = (process.env.FINQUANT_V02_TRAINING_REPORTS || "").trim();
  for (const p of env.split(",").map((s) => s.trim()).filter(Boolean)) {
    out.push(p);
  }
  out.push(path.join(REPO, "finquant", "reports", "full_training_report_v0.1.md"));
  out.push(path.join(REPO, "finquant", "reports", "full_training_report_v0.2.md"));
  out.push(
    path.join(FINQUANT_LEGACY_ROOT, "reports", "full_training_report_v0.1.md")
  );
  out.push(
    path.join(FINQUANT_LEGACY_ROOT, "reports", "full_training_report_v0.2.md")
  );
  return [...new Set(out)];
}

function readFinquantV02TrainingProofText(trainLogPath) {
  let combined = "";
  const optionalPaths = finquantV02OptionalReportPaths();
  try {
    if (fs.existsSync(trainLogPath)) {
      combined += fs.readFileSync(trainLogPath, "utf8");
    }
  } catch {
    /* ignore */
  }
  for (const p of optionalPaths) {
    try {
      if (fs.existsSync(p) && fs.statSync(p).isFile()) {
        combined += `\n${fs.readFileSync(p, "utf8")}`;
      }
    } catch {
      /* ignore */
    }
  }
  return { combined, optionalPaths };
}

/**
 * Training complete iff train_runtime plus any step-3000 signal (JSON steps, progress fraction, or step token).
 */
function detectFinquantV02TrainingProof(text) {
  const has_train_runtime = /\btrain_runtime\b/i.test(text);
  const has_steps_json = /"steps"\s*:\s*3000\b/.test(text);
  const has_step_token = /\bstep\s*[:=]?\s*3000\b/i.test(text);
  const has_progress_3000 = /\b3000\s*\/\s*3000\b/.test(text);
  const has_steps_3000 = has_steps_json || has_step_token;
  const steps_complete = has_steps_3000 || has_progress_3000;
  return {
    has_train_runtime,
    has_steps_3000,
    has_progress_3000,
    /** Same signals broken out for diagnostics */
    _has_steps_json: has_steps_json,
    _has_step_token: has_step_token,
    steps_complete,
    training_complete: has_train_runtime && steps_complete,
  };
}

/** Host-installed script under mounted /data/NDE/tools (Python/GPU on host via PATH or TRAIN_PYTHON). */
const HOST_FINQUANT_V02_EVAL = path.join(DATA_NDE, "tools", "run_finquant_v02_eval.sh");

function runHostFinquantV02Eval() {
  return new Promise((resolve, reject) => {
    const out = [];
    const err = [];
    const child = spawn(HOST_FINQUANT_V02_EVAL, [], {
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        REPO_ROOT: process.env.REPO_ROOT || REPO,
        FINQUANT_BASE: process.env.FINQUANT_BASE || FINQUANT_LEGACY_ROOT,
        TRAIN_PYTHON:
          process.env.TRAIN_PYTHON || "/data/NDE/.venv-train/bin/python",
      },
    });
    child.stdout.on("data", (c) => out.push(c));
    child.stderr.on("data", (c) => err.push(c));
    child.on("error", (e) => reject(e));
    child.on("close", (code, signal) => {
      resolve({
        code: code == null ? (signal ? 1 : 0) : code,
        stdout: Buffer.concat(out).toString("utf8"),
        stderr: Buffer.concat(err).toString("utf8"),
      });
    });
  });
}

function writeFinquantV02State(payload) {
  const { runDir, statePath, adapterPath, evalReport } = finquantV02Paths();
  fs.mkdirSync(runDir, { recursive: true });
  const doc = {
    domain: "finquant",
    version: "v0.2",
    train_ok: payload.train_ok,
    eval_passed: payload.eval_passed,
    certified: !!(payload.train_ok && payload.eval_passed),
    adapter_path: adapterPath,
    eval_report: evalReport,
  };
  if (payload.eval_summary) doc.eval_summary = payload.eval_summary;
  if (payload.last_error) doc.last_error = payload.last_error;
  doc.validated_at = new Date().toISOString();
  fs.writeFileSync(statePath, JSON.stringify(doc, null, 2));
  return doc;
}

// --- Upload storage: <nde>/<domain>/sources/raw ---
function uploadsDir(domain) {
  const raw = path.join(DATA_NDE, domain, "sources", "raw");
  fs.mkdirSync(raw, { recursive: true });
  return raw;
}

const storage = multer.diskStorage({
  destination(_req, _file, cb) {
    const dom = safeDomain(_req.params.domain);
    if (!dom) return cb(new Error("bad_domain"));
    cb(null, uploadsDir(dom));
  },
  filename(_req, file, cb) {
    const base = path.basename(file.originalname).replace(/[^a-zA-Z0-9._-]/g, "_");
    cb(null, `${Date.now()}_${base}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 80 * 1024 * 1024 },
  fileFilter(_req, file, cb) {
    const ext = path.extname(file.originalname).toLowerCase();
    if (ACCEPT_EXT.has(ext)) cb(null, true);
    else cb(new Error(`unsupported_type:${ext}`));
  },
});

function readStudioPackageSemver() {
  try {
    const p = path.join(__dirname, "package.json");
    const j = JSON.parse(fs.readFileSync(p, "utf8"));
    return typeof j.version === "string" ? j.version : "0.0.0";
  } catch {
    return "unknown";
  }
}

/** Matches package.json in the running container / repo checkout */
app.get("/api/studio-version", (_req, res) => {
  res.json({
    service: "nde-studio",
    semver: readStudioPackageSemver(),
    commit: process.env.NDE_STUDIO_COMMIT || "unknown",
  });
});

/**
 * FinQuant v0.2 — validate adapter + training proof, run eval_finquant.py, write NDE state.json.
 * Requires GPU + Python training stack where this Node process runs (e.g. trx40 host with deps installed).
 */
app.post("/api/finquant/validate-v02", async (_req, res) => {
  const { adapterPath, trainLog, evalReport, statePath } = finquantV02Paths();

  const reportExists = () =>
    finquantV02OptionalReportPaths().some((p) => {
      try {
        return fs.existsSync(p) && fs.statSync(p).isFile();
      } catch {
        return false;
      }
    });

  /** Set once training proof succeeds (used in eval catch responses). */
  let proofFields;

  try {
    const adapter_exists =
      fs.existsSync(adapterPath) && fs.statSync(adapterPath).isDirectory();

    if (!adapter_exists) {
      writeFinquantV02State({
        train_ok: false,
        eval_passed: false,
        last_error: `adapter_missing:${adapterPath}`,
      });
      return res.status(400).json({
        ok: false,
        step: "adapter",
        error: "adapter_missing",
        adapter_path: adapterPath,
        state_path: statePath,
        adapter_exists: false,
        report_exists: reportExists(),
        has_train_runtime: false,
        has_steps_3000: false,
        has_progress_3000: false,
      });
    }

    const { combined: trainBlob } = readFinquantV02TrainingProofText(trainLog);
    if (!trainBlob.trim()) {
      writeFinquantV02State({
        train_ok: false,
        eval_passed: false,
        last_error: `no_training_text:${trainLog}`,
      });
      return res.status(400).json({
        ok: false,
        step: "train_log",
        error: "no_training_content",
        train_log: trainLog,
        state_path: statePath,
        adapter_exists: true,
        report_exists: reportExists(),
        has_train_runtime: false,
        has_steps_3000: false,
        has_progress_3000: false,
      });
    }

    const proof = detectFinquantV02TrainingProof(trainBlob);
    proofFields = {
      has_train_runtime: proof.has_train_runtime,
      has_steps_3000: proof.has_steps_3000,
      has_progress_3000: proof.has_progress_3000,
      adapter_exists: true,
      report_exists: reportExists(),
    };

    if (!proof.training_complete) {
      writeFinquantV02State({
        train_ok: false,
        eval_passed: false,
        last_error: `training_incomplete:${JSON.stringify(proofFields)}`,
      });
      return res.status(400).json({
        ok: false,
        step: "training_proof",
        error: "training_not_complete",
        train_log: trainLog,
        state_path: statePath,
        ...proofFields,
      });
    }

    if (!fs.existsSync(HOST_FINQUANT_V02_EVAL)) {
      writeFinquantV02State({
        train_ok: true,
        eval_passed: false,
        last_error: `host_eval_script_missing:${HOST_FINQUANT_V02_EVAL}`,
      });
      return res.status(503).json({
        ok: false,
        step: "eval",
        error: "host_eval_script_missing",
        hint: "Install on host: bash scripts/install_nde_data_layout.sh /data/NDE",
        host_script: HOST_FINQUANT_V02_EVAL,
        state_path: statePath,
        ...proofFields,
      });
    }

    let evalResult;
    try {
      evalResult = await runHostFinquantV02Eval();
    } catch (spawnErr) {
      const msg = spawnErr?.message || String(spawnErr);
      try {
        writeFinquantV02State({
          train_ok: true,
          eval_passed: false,
          last_error: `eval_spawn:${msg.slice(0, 1200)}`,
        });
      } catch {
        /* ignore */
      }
      return res.status(500).json({
        ok: false,
        step: "eval",
        error: msg.slice(0, 8000),
        state_path: statePath,
        ...(proofFields ?? {}),
      });
    }

    const evalPassed = evalResult.code === 0;
    const parsed = evalResult.stdout
      ? parseEvalFinquantStdout(evalResult.stdout)
      : null;
    const summary = parsed?.summary;
    const casesPass = Number(summary?.cases_pass ?? 0);
    const casesTotal = Number(summary?.cases_total ?? 0);
    const evalSummary = {
      exit_code: evalResult.code,
      ...(summary
        ? {
            cases_pass: casesPass,
            cases_total: casesTotal,
            adapter: summary.adapter,
          }
        : {}),
    };

    const doc = writeFinquantV02State({
      train_ok: true,
      eval_passed: evalPassed,
      eval_summary: evalSummary,
      last_error: evalPassed
        ? undefined
        : `eval_exit_${evalResult.code}:${evalResult.stderr.slice(0, 2000)}`,
    });

    return res.json({
      ok: evalPassed,
      certified: doc.certified === true,
      eval_passed: doc.eval_passed,
      exit_code: evalResult.code,
      state_path: statePath,
      eval_report: evalReport,
      summary: evalSummary,
      stderr: evalResult.stderr ? evalResult.stderr.slice(-8000) : "",
      stdout_tail: evalResult.stdout ? evalResult.stdout.slice(-4000) : "",
      ...proofFields,
    });
  } catch (err) {
    const msg =
      (err && err.stderr && String(err.stderr)) ||
      (err && err.message) ||
      String(err);
    try {
      writeFinquantV02State({
        train_ok: true,
        eval_passed: false,
        last_error: `eval_exec:${msg.slice(0, 1200)}`,
      });
    } catch {
      /* ignore */
    }
    return res.status(500).json({
      ok: false,
      step: "eval",
      error: msg.slice(0, 8000),
      state_path: statePath,
      ...(proofFields ?? {}),
    });
  }
});

app.get("/api/domains", (_req, res) => {
  let discovered = ["secops", "finquant"];
  try {
    if (fs.existsSync(DATA_NDE)) {
      discovered = fs
        .readdirSync(DATA_NDE, { withFileTypes: true })
        .filter((e) => e.isDirectory())
        .map((e) => e.name)
        .filter((name) => !name.startsWith(".") && name !== "tools");
    }
  } catch {
    /* keep defaults */
  }
  res.json({
    domains: discovered.length ? discovered : ["secops", "finquant"],
    nde_root: DATA_NDE,
  });
});

app.get("/api/runs/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ error: "bad_domain" });
  const sorted = listRunsSorted(domain);
  const mtimeById = new Map(sorted.map((r) => [r.run_id, r.mtime]));
  const enriched = sorted.map((r) => {
    const pv = derivePipelineVisual(domain, r.run_id);
    const studio_status = pv?.run_list_badge ?? "UNKNOWN";
    return {
      run_id: r.run_id,
      path: r.path,
      studio_status,
      progress_percent: pv?.progress_percent ?? null,
    };
  });
  enriched.sort((a, b) => {
    const ra = runStatusSortRank(a.studio_status);
    const rb = runStatusSortRank(b.studio_status);
    if (ra !== rb) return ra - rb;
    return (mtimeById.get(b.run_id) ?? 0) - (mtimeById.get(a.run_id) ?? 0);
  });
  res.json({ domain, runs: enriched });
});

function buildDashboardPayload(domain) {
  const primary = resolveDashboardPrimaryRun(domain);
  const primaryRunId = primary.run_id;
  const primaryState = primary.state;
  const pv = primaryRunId ? derivePipelineVisual(domain, primaryRunId) : null;

  let certificateOnDisk = false;
  if (primaryRunId) {
    certificateOnDisk = fs.existsSync(
      path.join(runRoot(domain, primaryRunId), "CERTIFICATE.json")
    );
  }

  const stagingPath =
    primaryState?.staging_path ||
    primaryState?.artifacts?.staging_path ||
    null;

  const tcSummary = buildTrainingCycleSummary(domain);
  const primaryIsCycle = !!(primary.is_cycle && primaryRunId);

  const finquantLegacyState =
    domain === "finquant"
      ? readJsonSafe(path.join(runRoot(domain, LEGACY_FINQUANT_RUN_LABEL), "state.json"))
      : null;

  const stagingHint = extractStagingHintFromTrainingYaml(domain);
  const pipelineFields =
    primaryRunId && pv
      ? buildPipelineDashboardFields(
          domain,
          primaryRunId,
          primaryState,
          pv,
          tcSummary,
          primaryIsCycle,
          certificateOnDisk,
          stagingHint
        )
      : emptyPipelineDashboardFields();

  const base = {
    domain,
    selected_domain: domain,
    active_run_id: primaryRunId,
    latest_run_id: primaryRunId,
    primary_run_is_cycle_candidate: primaryIsCycle,
    prior_certified_run_id: primaryIsCycle ? tcSummary.latest_certified_run_id : null,
    prior_certified_version: primaryIsCycle ? tcSummary.latest_certified_version : null,
    progress_percent: pv?.progress_percent ?? 0,
    progress_label: pv?.progress_label ?? null,
    current_status: pv?.pipeline_status ?? (primaryState ? summarizeStatus(primaryState) : "no_runs"),
    dashboard_status_label: pv?.dashboard_status ?? null,
    latest_error: pv?.latest_error ?? null,
    active_job: pv?.active_job ?? null,
    certification_status: certificateOnDisk
      ? "issued"
      : primaryState?.certified
        ? "state_certified"
        : "none",
    certificate_on_disk: certificateOnDisk,
    state_snapshot: primaryState,
    staging_path_hint: stagingPath,
    training_log_tail: primaryRunId ? trainingLogTail(domain, primaryRunId) : "",
    finquant_v02:
      domain === "finquant"
        ? buildFinquantV02DashboardBlock(finquantLegacyState)
        : undefined,
    training_cycle: tcSummary,
    ...pipelineFields,
  };

  if (tcSummary.active_cycle && tcSummary.active_run_id === primaryRunId) {
    base.training_log_tail =
      tcSummary.active_cycle.log_tail || base.training_log_tail || "";
  }

  if (domain === "finquant") {
    const lf = buildFinquantLegacySection();
    const out = mergeFinquantDashboard(base, lf);
    return out;
  }
  return base;
}

/** Same payload as GET /api/dashboard/:domain with domain=finquant */
app.get("/api/dashboard/finquant", (_req, res) => {
  res.json(buildDashboardPayload("finquant"));
});

app.get("/api/dashboard/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ error: "bad_domain" });
  res.json(buildDashboardPayload(domain));
});

/**
 * Universal Advance Training Cycle — LangGraph via run_graph.sh only.
 * Body (optional JSON): { "mode": "smoke" | "full", "admin_approved": true } for full training.
 */
app.post("/api/advance/:domain", (req, res) => {
  const out = performAdvanceTrainingCycle(req.params.domain, req.body || {});
  res.status(out.status).json(out.json);
});

/** @deprecated Prefer POST /api/advance/:domain */
app.post("/api/nde/advance-cycle/:domain", (req, res) => {
  const out = performAdvanceTrainingCycle(req.params.domain, req.body || {});
  res.status(out.status).json(out.json);
});

app.get("/api/sources/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ error: "bad_domain" });
  const raw = uploadsDir(domain);
  const files = [];
  try {
    for (const name of fs.readdirSync(raw, { withFileTypes: true })) {
      if (!name.isFile()) continue;
      const fp = path.join(raw, name.name);
      const st = fs.statSync(fp);
      files.push({
        name: name.name,
        size: st.size,
        mtime: st.mtime.toISOString(),
      });
    }
  } catch (e) {
    return res.status(500).json({ error: String(e), files: [] });
  }
  files.sort((a, b) => b.name.localeCompare(a.name));
  res.json({ domain, upload_dir: raw, accepted_extensions: [...ACCEPT_EXT], files });
});

app.post("/api/upload/:domain", (req, res, next) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ ok: false, error: "bad_domain" });
  upload.array("files", 32)(req, res, (err) => {
    if (err) return next(err);
    const saved = (req.files || []).map((f) => ({
      originalname: f.originalname,
      path: f.path,
      size: f.size,
    }));
    res.json({ ok: true, domain, saved_count: saved.length, saved });
  });
});

app.post("/api/process/:domain", async (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ ok: false, error: "bad_domain" });
  const py = path.join(DATA_NDE, ".venv", "bin", "python");
  const script = path.join(DATA_NDE, "tools", "nde_source_processor.py");
  if (!fs.existsSync(py) || !fs.existsSync(script)) {
    return res.status(503).json({
      ok: false,
      error: "processor_not_available",
      detail: "Need /data/NDE/.venv and /data/NDE/tools/nde_source_processor.py",
    });
  }
  try {
    const { stdout, stderr } = await execFileAsync(
      py,
      [script, "--domain", domain, "--nde-root", DATA_NDE],
      { timeout: 600000, maxBuffer: 20 * 1024 * 1024, env: { ...process.env, NDE_ROOT: DATA_NDE } }
    );
    res.json({
      ok: true,
      domain,
      stdout_tail: (stdout || "").slice(-12000),
      stderr_tail: (stderr || "").slice(-8000),
    });
  } catch (e) {
    res.status(500).json({
      ok: false,
      error: String(e?.message || e),
      stderr: e?.stderr?.toString?.()?.slice(-8000) || "",
    });
  }
});

app.get("/api/datasets/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ error: "bad_domain" });
  const sorted = listRunsSorted(domain);
  const latestState = sorted[0]
    ? readJsonSafe(path.join(sorted[0].path, "state.json"))
    : null;
  const art = latestState?.artifacts || {};
  const stagingPath =
    latestState?.staging_path || art.staging_path || null;
  let rowCount = art.row_count ?? null;
  let missingSourceIds = art.missing_source_ids ?? null;
  let adversarialRatio = art.adversarial_ratio_observed ?? null;
  let processorReport = null;
  const reportGlob = path.join(DATA_NDE, domain, "reports");
  try {
    if (fs.existsSync(reportGlob)) {
      const reps = fs
        .readdirSync(reportGlob)
        .filter((n) => n.endsWith(".md") || n.endsWith(".json"))
        .map((n) => ({
          name: n,
          path: path.join(reportGlob, n),
          mtime: fs.statSync(path.join(reportGlob, n)).mtime.toISOString(),
        }));
      reps.sort((a, b) => b.mtime.localeCompare(a.mtime));
      if (reps[0]) {
        processorReport = {
          path: reps[0].path,
          preview: tailFile(reps[0].path, 8000),
        };
      }
    }
  } catch {
    /* ignore */
  }
  // Live row count from staging file if present
  if (stagingPath && fs.existsSync(stagingPath) && rowCount == null) {
    try {
      const txt = fs.readFileSync(stagingPath, "utf8");
      rowCount = txt.split("\n").filter((l) => l.trim()).length;
    } catch {
      /* */
    }
  }

  res.json({
    domain,
    staging_path: stagingPath,
    row_count: rowCount,
    missing_source_ids: missingSourceIds,
    adversarial_ratio: adversarialRatio,
    latest_processor_report: processorReport,
    source_ids_note:
      missingSourceIds != null
        ? `${missingSourceIds} rows missing source ids (from latest run artifacts)`
        : null,
  });
});

app.get("/api/run/:domain/:run_id", (req, res) => {
  const domain = safeDomain(req.params.domain);
  const runId = req.params.run_id;
  if (!domain || !runId || String(runId).includes("..") || String(runId).includes("/")) {
    return res.status(400).json({ error: "bad_params" });
  }
  const root = runRoot(domain, runId);
  const statePath = path.join(root, "state.json");
  const certPath = path.join(root, "CERTIFICATE.json");
  const out = {
    domain,
    run_id: runId,
    exists: fs.existsSync(root),
    state: null,
    certificate_present: fs.existsSync(certPath),
    nodes: listNodeStatuses(root),
    log_tail: trainingLogTail(domain, runId),
  };
  try {
    if (fs.existsSync(statePath)) {
      out.state = JSON.parse(fs.readFileSync(statePath, "utf8"));
    }
  } catch (e) {
    out.state_read_error = String(e);
  }
  res.json(out);
});

app.get("/api/exams/:domain/:run_id", (req, res) => {
  const domain = safeDomain(req.params.domain);
  const runId = req.params.run_id;
  if (!domain || !runId || String(runId).includes("..")) {
    return res.status(400).json({ error: "bad_params" });
  }
  const st = readJsonSafe(path.join(runRoot(domain, runId), "state.json"));
  if (!st) return res.json({ domain, run_id: runId, error: "no_state" });
  const evalScore = st.eval_score ?? null;
  const finalScore = st.final_exam_score ?? null;
  const pass =
    st.eval_passed !== false &&
    st.final_exam_passed !== false &&
    st.gate_passed !== false;
  res.json({
    domain,
    run_id: runId,
    eval_score: evalScore,
    final_exam_score: finalScore,
    eval_passed: st.eval_passed,
    final_exam_passed: st.final_exam_passed,
    gate_passed: st.gate_passed,
    overall_pass: !!pass,
    failing_cases: null,
    note:
      st.last_error && String(st.last_error).includes("fail")
        ? st.last_error
        : null,
  });
});

app.get("/api/settings/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ error: "bad_domain" });
  const domCfg = path.join(DATA_NDE, domain, "domain_config.yaml");
  const trainCfg = path.join(DATA_NDE, domain, "training", "config.yaml");
  res.json({
    domain,
    users_roles_placeholder: [{ user: "operator@local", role: "operator" }],
    model_config_yaml: fs.existsSync(trainCfg)
      ? tailFile(trainCfg, 16000)
      : null,
    domain_config_yaml: fs.existsSync(domCfg) ? tailFile(domCfg, 16000) : null,
    domain_config_path: fs.existsSync(domCfg) ? domCfg : null,
    training_config_path: fs.existsSync(trainCfg) ? trainCfg : null,
    full_training_requires_admin: true,
  });
});

app.post("/api/simulate/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ ok: false, error: "bad_domain" });
  res.json({
    ok: true,
    domain,
    message:
      "Invoke graph on host: /data/NDE/tools/run_graph.sh --domain ... --mode simulate (wired in future)",
    body: req.body ?? {},
  });
});

app.post("/api/train/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ ok: false, error: "bad_domain" });
  res.status(410).json({
    ok: false,
    error: "deprecated_use_advance_cycle",
    message:
      "Use POST /api/advance/:domain with JSON { \"mode\": \"smoke\" | \"full\", \"admin_approved\": true } for full.",
  });
});

const dist = path.join(__dirname, "dist");
app.use(express.static(dist, { index: false }));

app.get("*", (req, res, next) => {
  if (req.path.startsWith("/api")) return next();
  res.sendFile(path.join(dist, "index.html"), (err) => {
    if (err) next(err);
  });
});

app.use((err, req, res, _next) => {
  if (err instanceof multer.MulterError || err?.message?.startsWith("unsupported")) {
    return res.status(400).json({ ok: false, error: err.message || String(err) });
  }
  console.error(err);
  res.status(500).json({ error: "server_error" });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`NDE Studio listening on http://0.0.0.0:${PORT}`);
});
