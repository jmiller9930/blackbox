import { NavLink, Outlet } from "react-router-dom";
import { useEffect, useState } from "react";
import { studioVersionLabel } from "../buildMeta";
import { useStudio } from "../context/StudioContext";

const nav = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/sources", label: "Sources" },
  { to: "/datasets", label: "Datasets" },
  { to: "/runs", label: "Runs" },
  { to: "/exams", label: "Exams" },
  { to: "/settings", label: "Settings" },
];

type StudioVersionApi = { commit?: string; semver?: string };

export default function AppShell() {
  const { domains, domain, setDomain } = useStudio();
  const [gitShort, setGitShort] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/studio-version")
      .then((r) => (r.ok ? r.json() : null))
      .then((j: StudioVersionApi | null) => {
        if (cancelled || !j || typeof j.commit !== "string") return;
        const c = j.commit.trim();
        if (!c || c === "unknown") return;
        setGitShort(c.length > 7 ? c.slice(0, 7) : c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const versionBanner = [
    studioVersionLabel(),
    gitShort ? `git ${gitShort}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="shell-root">
      <header className="banner-wrap banner-full">
        <img
          className="banner-img"
          src="/finquant1/nde_studio_pattern.jpg"
          alt=""
        />
        <div className="banner-overlay banner-dark">
          <div className="banner-titles">
            <h1>NDE Studio</h1>
            <p
              className="banner-version mono"
              title="Semver from package.json; timestamp from vite build; git from container NDE_STUDIO_COMMIT."
            >
              {versionBanner}
            </p>
            <p className="banner-tagline">Control Plane</p>
          </div>
          <div className="user-box">
            <div>operator@local</div>
            <button type="button" className="btn-ghost" disabled title="Placeholder">
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="shell-body">
        <aside className="side-nav">
          <nav>
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `nav-link${isActive ? " nav-link-active" : ""}`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <div className="main-col">
          <div className="domain-bar">
            <label className="domain-label">
              Domain
              <select
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              >
                {domains.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <main className="page-main">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
