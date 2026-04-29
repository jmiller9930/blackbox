import { useCallback, useEffect, useState } from "react";
import { useStudio } from "../context/StudioContext";

type SourceList = {
  files?: { name: string; size: number; mtime: string }[];
  upload_dir?: string;
  accepted_extensions?: string[];
};

export default function Sources() {
  const { domain, refresh } = useStudio();
  const [data, setData] = useState<SourceList | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/sources/${encodeURIComponent(domain)}`);
      if (!r.ok) throw new Error(`${r.status}`);
      setData(await r.json());
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }, [domain]);

  useEffect(() => {
    void load();
  }, [load]);

  const uploadFiles = async (files: FileList | File[]) => {
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    setBusy("upload");
    try {
      const r = await fetch(`/api/upload/${encodeURIComponent(domain)}`, {
        method: "POST",
        body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      await load();
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (e.dataTransfer.files?.length) void uploadFiles(e.dataTransfer.files);
  };

  const processSources = async () => {
    setBusy("process");
    setErr(null);
    try {
      const r = await fetch(`/api/process/${encodeURIComponent(domain)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || JSON.stringify(j));
      await load();
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  };

  const ext = data?.accepted_extensions?.join(", ") ?? ".pdf, .md, …";

  return (
    <div className="page">
      <h2 className="page-title">Sources</h2>
      <p className="muted small">
        Raw inputs land under <code>sources/raw</code> for processing (
        <code>{data?.upload_dir ?? "…"}</code>).
      </p>
      {err && <p className="err">{err}</p>}

      <div className="row gap">
        <button
          type="button"
          className="btn-primary"
          disabled={!!busy}
          onClick={() => document.getElementById("file-up")?.click()}
        >
          Upload files
        </button>
        <input
          id="file-up"
          type="file"
          multiple
          className="hidden"
          accept=".pdf,.md,.txt,.json,.xml,.yaml,.yml"
          onChange={(e) => {
            if (e.target.files?.length) void uploadFiles(e.target.files);
          }}
        />
        <button
          type="button"
          className="btn-primary"
          disabled={!!busy}
          onClick={() => void processSources()}
        >
          Process sources
        </button>
      </div>

      <div
        className={`drop-zone${drag ? " drop-zone-active" : ""}`}
        onDragEnter={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
      >
        <p>
          Drag & drop files here · Accepted: {ext}
        </p>
      </div>

      <section className="card mt">
        <h3>Uploaded files</h3>
        {!data?.files?.length ? (
          <p className="muted">No files in raw queue.</p>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Name</th>
                <th>Size</th>
                <th>Modified</th>
              </tr>
            </thead>
            <tbody>
              {data.files.map((f) => (
                <tr key={f.name}>
                  <td className="mono">{f.name}</td>
                  <td>{f.size}</td>
                  <td className="small">{f.mtime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {busy && <p className="small muted">Working: {busy}…</p>}
    </div>
  );
}
