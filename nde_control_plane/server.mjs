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

app.get("/api/dashboard/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ error: "bad_domain" });
  const sorted = listRunsSorted(domain);
  const latest = sorted[0]?.run_id ?? null;
  let state = null;
  let cert = false;
  let lastErr = "";
  if (latest) {
    const rr = runRoot(domain, latest);
    state = readJsonSafe(path.join(rr, "state.json"));
    cert = fs.existsSync(path.join(rr, "CERTIFICATE.json"));
    lastErr = state?.last_error != null ? String(state.last_error) : "";
  }
  const stagingPath =
    state?.staging_path ||
    state?.artifacts?.staging_path ||
    null;

  res.json({
    domain,
    selected_domain: domain,
    active_run_id: latest,
    latest_run_id: latest,
    progress_percent: progressPct(state),
    current_status: state
      ? summarizeStatus(state)
      : "no_runs",
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
  });
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
