import { useCallback, useState, type ReactNode } from "react";

const STORAGE_PREFIX = "nde-studio.panel.v1";

type Props = {
  /** Per-browser key; include domain so FinQuant vs SecOps prefs stay separate. */
  panelKey: string;
  title: string;
  className?: string;
  children: ReactNode;
};

/**
 * Dashboard panel with caret toggle. Default collapsed; remembers open/closed in localStorage.
 */
export function CollapsibleDashboardSection({
  panelKey,
  title,
  className,
  children,
}: Props) {
  const [open, setOpen] = useState(() => {
    try {
      const v = localStorage.getItem(`${STORAGE_PREFIX}:${panelKey}`);
      if (v === "open") return true;
      if (v === "closed") return false;
    } catch {
      /* ignore */
    }
    return false;
  });

  const toggle = useCallback(() => {
    setOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(`${STORAGE_PREFIX}:${panelKey}`, next ? "open" : "closed");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return (
    <section className={className ?? "card wide"}>
      <button
        type="button"
        className="collapse-panel-header"
        aria-expanded={open}
        onClick={toggle}
      >
        <span className="collapse-caret" aria-hidden>
          {open ? "▼" : "▶"}
        </span>
        {title}
      </button>
      {open ? <div className="collapse-panel-body">{children}</div> : null}
    </section>
  );
}
