/**
 * Full-training telemetry helpers (mirrors nde/tools/nde_validation_lib.py resolve order).
 * Display-only — keep in sync with Python resolver. No PyYAML: regex parse only.
 */
import fs from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

const FINQUANT_PROGRESSIVE_BASELINE = "v0.2c_combined.jsonl";
const FINQUANT_LEGACY_PROGRESSIVE = "/data/finquant-1/datasets/staging/v0.2c_combined.jsonl";

function readUtf8Safe(p) {
  try {
    if (!fs.existsSync(p)) return "";
    return fs.readFileSync(p, "utf8");
  } catch {
    return "";
  }
}

function resolveUserDataPath(spec, domainBase) {
  const s = String(spec || "").trim();
  if (!s) return path.join(domainBase, "__invalid_empty__");
  if (path.isAbsolute(s)) return path.normalize(s);
  return path.normalize(path.join(domainBase, s));
}

/** Mirrors nde_validation_lib._training_yaml_staging_candidates (dataset, then data.staging_jsonl). */
function trainingYamlStagingCandidates(domainBase, tcPath) {
  const out = [];
  if (!fs.existsSync(tcPath)) return out;
  const txt = readUtf8Safe(tcPath).slice(0, 48000);
  for (const line of txt.split("\n")) {
    const md = line.match(/^\s*dataset\s*:\s*["']?([^"'\n#]+)/i);
    if (md) {
      out.push(resolveUserDataPath(md[1].trim().replace(/["']\s*$/, ""), domainBase));
      break;
    }
  }
  let inData = false;
  let dataIndent = null;
  for (const line of txt.split("\n")) {
    if (/^\s*data\s*:\s*(#|$)/i.test(line)) {
      inData = true;
      dataIndent = line.match(/^(\s*)/)?.[1]?.length ?? 0;
      continue;
    }
    if (inData) {
      const trimmed = line.trim();
      const ind = line.match(/^(\s*)/)?.[1]?.length ?? 0;
      if (
        trimmed &&
        !trimmed.startsWith("#") &&
        dataIndent != null &&
        ind <= dataIndent &&
        !/^\s*data\s*:/i.test(line)
      ) {
        inData = false;
        continue;
      }
      const ms = line.match(/^\s*staging_jsonl\s*:\s*["']?([^"'\n#]+)/i);
      if (ms) {
        out.push(resolveUserDataPath(ms[1].trim().replace(/["']\s*$/, ""), domainBase));
        break;
      }
    }
  }
  return out;
}

/** Mirrors domain_cfg output.staging_filename. */
function domainConfigStagingFilename(domainConfigPath) {
  if (!fs.existsSync(domainConfigPath)) return null;
  const txt = readUtf8Safe(domainConfigPath).slice(0, 24000);
  const m = txt.match(/staging_filename\s*:\s*["']?([^"'\n#]+)/im);
  return m ? m[1].trim().replace(/["']\s*$/, "") : null;
}

/**
 * @returns {{ path: string | null, source: string, config_paths_tried: string[] }}
 */
export function resolveStagingJsonlWithSource(ndeRoot, domain) {
  const base = path.join(ndeRoot, domain);
  const tc = path.join(base, "training", "config.yaml");
  const configCandidates = trainingYamlStagingCandidates(base, tc);

  for (const cand of configCandidates) {
    if (fs.existsSync(cand) && fs.statSync(cand).isFile()) {
      return {
        path: cand,
        source: "config",
        config_paths_tried: configCandidates,
      };
    }
  }

  if (domain === "secops") {
    for (const name of [
      "secops_nist_v0.3_from_sources.jsonl",
      "secops_cmmc_v0.3_from_sources.jsonl",
      "secops_v0.1.jsonl",
    ]) {
      const p = path.join(ndeRoot, "secops", "datasets", "staging", name);
      if (fs.existsSync(p)) {
        return { path: p, source: "canonical", config_paths_tried: configCandidates };
      }
    }
  }

  if (domain === "finquant") {
    const fb = path.join(base, "datasets", "staging", FINQUANT_PROGRESSIVE_BASELINE);
    if (fs.existsSync(fb)) {
      return { path: fb, source: "canonical", config_paths_tried: configCandidates };
    }
    if (fs.existsSync(FINQUANT_LEGACY_PROGRESSIVE)) {
      return {
        path: FINQUANT_LEGACY_PROGRESSIVE,
        source: "legacy_fallback",
        config_paths_tried: configCandidates,
      };
    }
    for (const name of ["finquant_v0.3_from_sources.jsonl", "finquant_staging_v0.1.jsonl"]) {
      const p = path.join(base, "datasets", "staging", name);
      if (fs.existsSync(p)) {
        return { path: p, source: "canonical", config_paths_tried: configCandidates };
      }
    }
  }

  const domCfg = path.join(base, "domain_config.yaml");
  const outFn = domainConfigStagingFilename(domCfg);
  if (outFn) {
    const p = path.join(base, "datasets", "staging", outFn);
    if (fs.existsSync(p)) {
      return { path: p, source: "canonical", config_paths_tried: configCandidates };
    }
  }

  return { path: null, source: "none", config_paths_tried: configCandidates };
}

/** Classify an on-disk path against resolver buckets (for run_state paths). */
export function classifyDatasetPath(datasetPath, resolved) {
  if (!datasetPath) {
    return {
      path: null,
      source: resolved.source !== "none" ? resolved.source : "canonical",
    };
  }
  const norm = path.normalize(datasetPath);
  if (resolved.path && path.normalize(resolved.path) === norm) {
    return { path: datasetPath, source: resolved.source };
  }
  for (const c of resolved.config_paths_tried || []) {
    if (path.normalize(c) === norm) return { path: datasetPath, source: "config" };
  }
  if (path.normalize(FINQUANT_LEGACY_PROGRESSIVE) === norm) {
    return { path: datasetPath, source: "legacy_fallback" };
  }
  return { path: datasetPath, source: "config" };
}

export function countJsonlRows(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return 0;
  try {
    const txt = readUtf8Safe(filePath);
    return txt.split("\n").filter((l) => l.trim()).length;
  } catch {
    return 0;
  }
}

export function pickTrainingNodeDirs(_domain, runId, ndeRoot, modeFull) {
  const rr = path.join(ndeRoot, _domain, "runs", runId);
  const ftDir = path.join(rr, "nodes", "full_train");
  const smDir = path.join(rr, "nodes", "smoke_train");
  const ftStdout = path.join(ftDir, "stdout.log");
  const smStdout = path.join(smDir, "stdout.log");
  if (fs.existsSync(ftStdout) || fs.existsSync(path.join(ftDir, "node_status.json"))) {
    return { disk: "full_train", logDir: "full_train" };
  }
  if (fs.existsSync(smStdout) || fs.existsSync(path.join(smDir, "node_status.json"))) {
    return { disk: "smoke_train", logDir: "smoke_train" };
  }
  return {
    disk: modeFull ? "full_train" : "smoke_train",
    logDir: modeFull ? "full_train" : "smoke_train",
  };
}

function tailFileEnd(p, maxBytes = 96000) {
  try {
    if (!fs.existsSync(p)) return "";
    const st = fs.statSync(p);
    const sz = st.size;
    const fd = fs.openSync(p, "r");
    try {
      const readSz = Math.min(maxBytes, sz);
      const buf = Buffer.alloc(readSz);
      const start = Math.max(0, sz - readSz);
      fs.readSync(fd, buf, 0, readSz, start);
      return buf.toString("utf8");
    } finally {
      fs.closeSync(fd);
    }
  } catch {
    return "";
  }
}

export function tailTrainingLogs(domain, runId, ndeRoot, logDir, maxBytes = 96000) {
  const rr = path.join(ndeRoot, domain, "runs", runId);
  const parts = [];
  const appendDir = (dir) => {
    for (const log of ["stdout.log", "stderr.log"]) {
      const p = path.join(rr, "nodes", dir, log);
      const t = tailFileEnd(p, maxBytes);
      if (t) parts.push(`=== ${dir}/${log} ===\n${t}`);
    }
  };
  appendDir(logDir);
  if (parts.length === 0) {
    const altDir = logDir === "full_train" ? "smoke_train" : "full_train";
    appendDir(altDir);
  }
  return parts.join("\n\n").trim();
}

export function parseTrainerFromLog(text) {
  if (!text) {
    return {
      checkpoint_shards_loaded: null,
      checkpoint_shards_total: null,
      train_step_current: null,
      train_step_total: null,
      progress_percent: null,
      epoch: null,
      loss: null,
      learning_rate: null,
      mean_token_accuracy: null,
    };
  }
  const chunk = text.length > 512000 ? text.slice(-512000) : text;

  let shardsLoaded = null;
  let shardsTotal = null;
  const shardRe = /Loading checkpoint shards:\s*(\d+)\s*\/\s*(\d+)/gi;
  let m;
  while ((m = shardRe.exec(chunk)) !== null) {
    shardsLoaded = parseInt(m[1], 10);
    shardsTotal = parseInt(m[2], 10);
  }

  let trainCur = null;
  let trainTot = null;
  const stepRe = /(\d+)\s*\/\s*(\d+)\b/g;
  while ((m = stepRe.exec(chunk)) !== null) {
    const cur = parseInt(m[1], 10);
    const tot = parseInt(m[2], 10);
    if (tot > 0 && tot < 1e9 && cur >= 0 && (tot >= 50 || tot === 3000)) {
      trainCur = cur;
      trainTot = tot;
    }
  }

  let epoch = null;
  let loss = null;
  let lr = null;
  let mta = null;
  const dictCandidates = chunk.match(/\{['"]loss['"][\s\S]{0,1800}?\}/g);
  if (dictCandidates && dictCandidates.length) {
    const last = dictCandidates[dictCandidates.length - 1];
    const ep =
      /['"]epoch['"]:\s*([\d.]+)/.exec(last) || /'epoch':\s*([\d.]+)/.exec(last);
    const ls =
      /['"]loss['"]:\s*([\d.eE+-]+)/.exec(last) || /'loss':\s*([\d.eE+-]+)/.exec(last);
    const lrn =
      /['"]learning_rate['"]:\s*([\d.eE+-]+)/.exec(last) ||
      /'learning_rate':\s*([\d.eE+-]+)/.exec(last);
    const mt =
      /['"]mean_token_accuracy['"]:\s*([\d.eE+-]+)/.exec(last) ||
      /'mean_token_accuracy':\s*([\d.eE+-]+)/.exec(last);
    if (ep) epoch = parseFloat(ep[1]);
    if (ls) loss = parseFloat(ls[1]);
    if (lrn) lr = parseFloat(lrn[1]);
    if (mt) mta = parseFloat(mt[1]);
  }

  let progress_percent =
    trainCur != null && trainTot != null && trainTot > 0
      ? Math.round((trainCur / trainTot) * 1000) / 10
      : null;

  return {
    checkpoint_shards_loaded: shardsLoaded,
    checkpoint_shards_total: shardsTotal,
    train_step_current: trainCur,
    train_step_total: trainTot,
    progress_percent,
    epoch,
    loss,
    learning_rate: lr,
    mean_token_accuracy: mta,
  };
}

export async function sampleNvidiaSmi() {
  try {
    const { stdout } = await execFileAsync(
      "nvidia-smi",
      [
        "--query-gpu=name,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
      ],
      { timeout: 6000, maxBuffer: 256 * 1024 }
    );
    const line = stdout.trim().split("\n")[0];
    if (!line) return null;
    const parts = line.split(",").map((s) => s.trim());
    return {
      gpu_name: parts[0] || null,
      vram_used_mb: parts[1] ? Number(parts[1]) : null,
      vram_total_mb: parts[2] ? Number(parts[2]) : null,
      gpu_util_pct: parts[3] ? Number(parts[3]) : null,
    };
  } catch {
    return null;
  }
}

export function formatEtaMs(etaMs) {
  if (!Number.isFinite(etaMs) || etaMs <= 0) return null;
  const s = Math.floor(etaMs / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

/** Regex-only parse of model + full-training adapter output_dir (FinQuant-style YAML). */
export function extractTrainingConfigHints(ndeRoot, repoRoot, domain) {
  const candidates = [
    path.join(ndeRoot, domain, "training", "config.yaml"),
    path.join(ndeRoot, domain, "training", "config_v0.1.yaml"),
    path.join(repoRoot, "finquant", "training", "config_v0.1.yaml"),
  ];
  let txt = "";
  for (const c of candidates) {
    if (fs.existsSync(c)) {
      txt = readUtf8Safe(c).slice(0, 96000);
      break;
    }
  }
  const base =
    (txt.match(/^\s*model_name_or_path\s*:\s*([^\n#]+)/im) || [])[1]?.trim().replace(
      /^["']|["']$/g,
      ""
    ) || null;
  let adapter = null;
  const fi = txt.search(/^\s*full\s*:/im);
  if (fi >= 0) {
    const sub = txt.slice(fi, fi + 4000);
    const om = sub.match(/^\s*output_dir\s*:\s*([^\n#]+)/im);
    if (om) adapter = om[1].trim().replace(/^["']|["']$/g, "");
  }
  return { base_model: base, adapter_output_full: adapter };
}
