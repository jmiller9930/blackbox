/**
 * NDE Studio — API backed by /data/NDE filesystem (+ optional /repo).
 */
import express from "express";
import fs from "fs";
import multer from "multer";
import path from "path";
import { execFile } from "child_process";
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

function resolveFinquantLatestRunAndState(sorted) {
  const v02RunId = LEGACY_FINQUANT_RUN_LABEL;
  const v02StatePath = path.join(runRoot("finquant", v02RunId), "state.json");
  if (fs.existsSync(v02StatePath)) {
    return {
      latest: v02RunId,
      state: readJsonSafe(v02StatePath),
    };
  }
  const latest = sorted[0]?.run_id ?? null;
  if (!latest) return { latest: null, state: null };
  return {
    latest,
    state: readJsonSafe(path.join(runRoot("finquant", latest), "state.json")),
  };
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
  });
});

/**
 * FinQuant v0.2 — validate adapter + training proof, run eval_finquant.py, write NDE state.json.
 * Requires GPU + Python training stack where this Node process runs (e.g. trx40 host with deps installed).
 */
app.post("/api/finquant/validate-v02", async (_req, res) => {
  const { adapterPath, trainLog, evalReport, statePath } = finquantV02Paths();
  const evalScript = path.join(REPO, "finquant", "evals", "eval_finquant.py");

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

    if (!fs.existsSync(evalScript)) {
      writeFinquantV02State({
        train_ok: true,
        eval_passed: false,
        last_error: "eval_script_missing_under_REPO_MOUNT",
      });
      return res.status(503).json({
        ok: false,
        step: "eval",
        error: "eval_script_missing",
        eval_script: evalScript,
        state_path: statePath,
        ...proofFields,
      });
    }

    const { stdout, stderr } = await execFileAsync(
      "python3",
      [
        evalScript,
        "--adapter",
        adapterPath,
        "--write-report",
        "--report-path",
        evalReport,
      ],
      {
        cwd: REPO,
        env: {
          ...process.env,
          FINQUANT_BASE: FINQUANT_LEGACY_ROOT,
        },
        maxBuffer: 64 * 1024 * 1024,
        timeout: 3_600_000,
      }
    );

    const parsed = parseEvalFinquantStdout(stdout);
    const summary = parsed?.summary;
    const casesPass = Number(summary?.cases_pass ?? 0);
    const casesTotal = Number(summary?.cases_total ?? 0);
    const evalPassed =
      Number.isFinite(casesTotal) &&
      casesTotal > 0 &&
      casesPass === casesTotal;

    const evalSummary = summary
      ? {
          cases_pass: casesPass,
          cases_total: casesTotal,
          adapter: summary.adapter,
        }
      : undefined;

    const doc = writeFinquantV02State({
      train_ok: true,
      eval_passed: evalPassed,
      eval_summary: evalSummary,
      last_error: evalPassed
        ? undefined
        : `eval_cases:${casesPass}/${casesTotal}`,
    });

    return res.json({
      ok: true,
      certified: doc.certified === true,
      eval_passed: doc.eval_passed,
      state_path: statePath,
      eval_report: evalReport,
      summary: evalSummary,
      stderr: stderr ? String(stderr).slice(-4000) : "",
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
  res.json({
    domain,
    runs: sorted.map((r) => ({ run_id: r.run_id, path: r.path })),
  });
});

function buildDashboardPayload(domain) {
  const sorted = listRunsSorted(domain);
  let latest = sorted[0]?.run_id ?? null;
  let state = null;

  if (domain === "finquant") {
    const r = resolveFinquantLatestRunAndState(sorted);
    latest = r.latest;
    state = r.state;
  } else if (sorted.length) {
    latest = sorted[0].run_id;
    state = readJsonSafe(path.join(runRoot(domain, latest), "state.json"));
  }

  let cert = false;
  let lastErr = "";
  if (latest) {
    cert = fs.existsSync(path.join(runRoot(domain, latest), "CERTIFICATE.json"));
    lastErr = state?.last_error != null ? String(state.last_error) : "";
  }
  const stagingPath =
    state?.staging_path ||
    state?.artifacts?.staging_path ||
    null;

  const base = {
    domain,
    selected_domain: domain,
    active_run_id: latest,
    latest_run_id: latest,
    progress_percent: progressPct(state),
    current_status: state ? summarizeStatus(state) : "no_runs",
    latest_error: lastErr || null,
    certification_status: cert
      ? "issued"
      : state?.certified
        ? "state_certified"
        : "none",
    certificate_on_disk: cert,
    state_snapshot: state,
    staging_path_hint: stagingPath,
    training_log_tail: latest ? trainingLogTail(domain, latest) : "",
    finquant_v02:
      domain === "finquant" ? buildFinquantV02DashboardBlock(state) : undefined,
  };

  if (domain === "finquant") {
    const lf = buildFinquantLegacySection();
    return mergeFinquantDashboard(base, lf);
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
  const mode = req.body?.mode || "smoke";
  const needAdmin = mode === "full";
  if (needAdmin && !req.body?.admin_approved) {
    return res.status(403).json({
      ok: false,
      error: "admin_approval_required",
      message: "Full training requires admin approval in UI",
    });
  }
  res.json({
    ok: true,
    domain,
    mode,
    message:
      "Training is started via run_graph.sh on the host (not executed inside this container).",
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
