/**
 * NDE Studio — static UI + API placeholders.
 * Mounts: /data/NDE (runtime), /repo (blackbox checkout) for future wiring.
 */
import express from "express";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3999);
const DATA_NDE = process.env.NDE_DATA_ROOT || "/data/NDE";
const REPO = process.env.REPO_MOUNT || "/repo";

const app = express();
app.use(express.json({ limit: "32mb" }));

function safeDomain(d) {
  if (!d || typeof d !== "string") return null;
  const t = d.replace(/[^a-z0-9_-]/gi, "");
  return t === d && d.length > 0 ? d : null;
}

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
    placeholder: true,
    nde_root: DATA_NDE,
  });
});

app.get("/api/runs/:domain", (req, res) => {
  const domain = safeDomain(req.params.domain);
  if (!domain) return res.status(400).json({ error: "bad_domain" });
  const runsDir = path.join(DATA_NDE, domain, "runs");
  const runs = [];
  try {
    if (fs.existsSync(runsDir)) {
      for (const name of fs.readdirSync(runsDir, { withFileTypes: true })) {
        if (name.isDirectory()) {
          runs.push({
            run_id: name.name,
            path: path.join(runsDir, name.name),
          });
        }
      }
    }
  } catch (e) {
    return res.status(500).json({ error: String(e), runs: [] });
  }
  res.json({ domain, runs, placeholder: true });
});

app.get("/api/run/:domain/:run_id", (req, res) => {
  const domain = safeDomain(req.params.domain);
  const runId = req.params.run_id;
  if (!domain || !runId || String(runId).includes("..") || String(runId).includes("/")) {
    return res.status(400).json({ error: "bad_params" });
  }
  const root = path.join(DATA_NDE, domain, "runs", runId);
  const statePath = path.join(root, "state.json");
  const certPath = path.join(root, "CERTIFICATE.json");
  const out = {
    domain,
    run_id: runId,
    placeholder: true,
    exists: fs.existsSync(root),
    state: null,
    certificate_present: fs.existsSync(certPath),
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

function postPlaceholder(kind) {
  return (req, res) => {
    const domain = safeDomain(req.params.domain);
    if (!domain) return res.status(400).json({ ok: false, error: "bad_domain" });
    res.json({
      ok: true,
      placeholder: true,
      kind,
      domain,
      body: req.body ?? {},
      message: `${kind} not wired to backend yet; use CLI or future integration.`,
      nde_root: DATA_NDE,
      repo: REPO,
    });
  };
}

app.post("/api/upload/:domain", postPlaceholder("upload"));
app.post("/api/process/:domain", postPlaceholder("process"));
app.post("/api/simulate/:domain", postPlaceholder("simulate"));
app.post("/api/train/:domain", postPlaceholder("train"));

const dist = path.join(__dirname, "dist");
app.use(express.static(dist, { index: false }));

app.get("*", (req, res, next) => {
  if (req.path.startsWith("/api")) return next();
  res.sendFile(path.join(dist, "index.html"), (err) => {
    if (err) next(err);
  });
});

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).send("Server error");
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`NDE Studio listening on http://0.0.0.0:${PORT}`);
});
