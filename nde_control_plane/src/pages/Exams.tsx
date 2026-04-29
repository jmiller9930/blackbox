import { useEffect, useState } from "react";
import { useStudio } from "../context/StudioContext";

type ExamPayload = {
  eval_score?: number | null;
  final_exam_score?: number | null;
  eval_passed?: boolean;
  final_exam_passed?: boolean;
  overall_pass?: boolean;
  failing_cases?: unknown;
  note?: string | null;
};

export default function Exams() {
  const { domain, selectedRunId } = useStudio();
  const [ex, setEx] = useState<ExamPayload | null>(null);

  useEffect(() => {
    if (!selectedRunId) {
      setEx(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch(
          `/api/exams/${encodeURIComponent(domain)}/${encodeURIComponent(selectedRunId)}`
        );
        if (!r.ok) throw new Error(`${r.status}`);
        const j = (await r.json()) as ExamPayload;
        if (!cancelled) setEx(j);
      } catch {
        if (!cancelled) setEx(null);
      }
    };
    void load();
    const t = window.setInterval(load, 2600);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [domain, selectedRunId]);

  return (
    <div className="page">
      <h2 className="page-title">Exams</h2>
      {!selectedRunId ? (
        <p className="muted">
          Select a run on the Runs page (auto-selected when available).
        </p>
      ) : !ex ? (
        <p className="muted">Loading exam summary…</p>
      ) : (
        <div className="grid-cards">
          <section className="card">
            <h3>Eval score</h3>
            <p className="mono accent large">
              {ex.eval_score != null ? ex.eval_score : "—"}
            </p>
          </section>
          <section className="card">
            <h3>Final exam score</h3>
            <p className="mono accent large">
              {ex.final_exam_score != null ? ex.final_exam_score : "—"}
            </p>
          </section>
          <section className="card wide">
            <h3>Pass / fail</h3>
            <p className="mono">
              Eval:{" "}
              <strong>{ex.eval_passed === undefined ? "—" : String(!!ex.eval_passed)}</strong>
              {" · "}
              Final:{" "}
              <strong>
                {ex.final_exam_passed === undefined
                  ? "—"
                  : String(!!ex.final_exam_passed)}
              </strong>
              {" · "}
              Overall:{" "}
              <strong className={ex.overall_pass ? "ok" : "warn"}>
                {ex.overall_pass ? "PASS" : "FAIL"}
              </strong>
            </p>
          </section>
          <section className="card wide">
            <h3>Failing cases</h3>
            {ex.note ? (
              <pre className="log-pre">{ex.note}</pre>
            ) : (
              <p className="muted">
                No structured failing-case payload (see run proofs / harness JSON).
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
