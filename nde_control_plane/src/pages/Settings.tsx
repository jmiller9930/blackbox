import { useEffect, useState } from "react";
import { useStudio } from "../context/StudioContext";

type SettingsPayload = {
  users_roles_placeholder?: { user: string; role: string }[];
  model_config_yaml?: string | null;
  domain_config_yaml?: string | null;
  domain_config_path?: string | null;
  training_config_path?: string | null;
};

export default function Settings() {
  const { domain, refresh } = useStudio();
  const [data, setData] = useState<SettingsPayload | null>(null);
  const [adminApproval, setAdminApproval] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch(`/api/settings/${encodeURIComponent(domain)}`);
        if (r.ok) setData(await r.json());
      } catch {
        setData(null);
      }
    })();
  }, [domain]);

  const fireTrain = async (mode: string) => {
    setBusy(mode);
    setMsg(null);
    try {
      const body: Record<string, unknown> = { mode };
      if (mode === "full") body.admin_approved = adminApproval;
      const r = await fetch(`/api/train/${encodeURIComponent(domain)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      setMsg(JSON.stringify(j, null, 2));
      await refresh();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">Settings</h2>

      <section className="card">
        <h3>Users / roles (placeholder)</h3>
        <ul className="mono">
          {(data?.users_roles_placeholder ?? []).map((u) => (
            <li key={u.user}>
              {u.user} — {u.role}
            </li>
          ))}
        </ul>
      </section>

      <section className="card mt">
        <h3>Model config</h3>
        <p className="small muted">{data?.training_config_path ?? "—"}</p>
        <pre className="log-pre">
          {data?.model_config_yaml ?? "No training/config.yaml on disk."}
        </pre>
      </section>

      <section className="card mt">
        <h3>Domain config</h3>
        <p className="small muted">{data?.domain_config_path ?? "—"}</p>
        <pre className="log-pre">
          {data?.domain_config_yaml ?? "No domain_config.yaml on disk."}
        </pre>
      </section>

      <section className="card mt">
        <h3>Training controls</h3>
        <p className="small muted">
          Graph/training is executed on the host via{" "}
          <code>/data/NDE/tools/run_graph.sh</code>. Buttons hit API stubs;
          wire SSH/host runner separately.
        </p>
        <div className="row gap wrap mt">
          <button
            type="button"
            className="btn-primary"
            disabled={!!busy}
            onClick={() => void fireTrain("smoke")}
          >
            Smoke training (API)
          </button>
          <label className="inline-check">
            <input
              type="checkbox"
              checked={adminApproval}
              onChange={(e) => setAdminApproval(e.target.checked)}
            />
            Admin approval for full training
          </label>
          <button
            type="button"
            className="btn-danger"
            disabled={!!busy || !adminApproval}
            onClick={() => void fireTrain("full")}
          >
            Full training (API)
          </button>
        </div>
        {msg && <pre className="json-pre mt">{msg}</pre>}
      </section>
    </div>
  );
}
