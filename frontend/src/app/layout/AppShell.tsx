import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import blueAlphaLogo from "../../assets/bluealpha_mark_blue.png";
import { buildHistoryResultsPath, buildResultsPath, readActiveResultsRunId } from "../../features/results/data/resultLoader";
import { ContextualHelpDrawer, openContextualHelp, type HelpSectionId } from "../../shared/ContextualHelp";
import { monitorNavItem, resultNavItems, workflowNavItems } from "../navigation";

type SetupStepState = "completed" | "active" | "upcoming";

const workflowStepLabels = ["01", "02", "03", "04", "05", "06"];

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? "nav-link nav-link--active" : "nav-link";

export function AppShell() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [activeHelpSection, setActiveHelpSection] = useState<HelpSectionId | null>(null);
  const location = useLocation();

  const closeDrawer = () => setIsDrawerOpen(false);
  const closeHelp = () => setIsHelpOpen(false);

  useEffect(() => {
    setIsDrawerOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    setIsHelpOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const handleOpenHelp = (event: Event) => {
      const detail = (event as CustomEvent<{ sectionId?: HelpSectionId }>).detail;
      setActiveHelpSection(detail?.sectionId ?? null);
      setIsHelpOpen(true);
    };

    window.addEventListener("bluealpha:open-help", handleOpenHelp);
    return () => window.removeEventListener("bluealpha:open-help", handleOpenHelp);
  }, []);

  useEffect(() => {
    if (!isDrawerOpen && !isHelpOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsDrawerOpen(false);
        setIsHelpOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isDrawerOpen, isHelpOpen]);

  const activeWorkflowIndex = workflowNavItems.findIndex((item) => location.pathname.startsWith(item.path));
  const setupIsComplete = location.pathname.startsWith("/runs") || location.pathname.startsWith("/results");
  const resultPathRunSegment = location.pathname.match(/^\/results\/([^/]+)/)?.[1] || "";
  const resultRouteSlugs = new Set(resultNavItems.map((item) => item.path.replace("/results/", "")));
  const searchParams = new URLSearchParams(location.search);
  const currentHistoryId = searchParams.get("history_id");
  const currentRunId =
    searchParams.get("run_id") ||
    (resultRouteSlugs.has(resultPathRunSegment) ? "" : resultPathRunSegment) ||
    readActiveResultsRunId();
  const resultPath = (path: string) => {
    if (path === "/results/history") {
      return path;
    }
    return currentHistoryId ? buildHistoryResultsPath(path, currentHistoryId) : buildResultsPath(path, currentRunId);
  };

  const setupStepState = (index: number): SetupStepState => {
    if (setupIsComplete || (activeWorkflowIndex > -1 && index < activeWorkflowIndex)) {
      return "completed";
    }

    if (index === activeWorkflowIndex) {
      return "active";
    }

    return "upcoming";
  };

  return (
    <div className={isDrawerOpen ? "app-shell app-shell--drawer-open" : "app-shell"}>
      <aside className="sidebar" aria-label="Application navigation" aria-hidden={!isDrawerOpen}>
        <div className="brand">
          <img className="brand-mark" src={blueAlphaLogo} alt="" aria-hidden="true" />
          <div>
            <div className="brand-title">Bayesian MMM Prior Sensitivity Dashboard</div>
          </div>
          <button className="drawer-close-button" type="button" aria-label="Close navigation" onClick={closeDrawer}>
            <span aria-hidden="true" />
          </button>
        </div>

        <nav className="nav-stack">
          <section className="nav-group" aria-labelledby="workflow-nav-heading">
            <h2 id="workflow-nav-heading">Setup</h2>
            <p className="nav-group-helper">Complete these steps in order to launch a run.</p>
            <ol className="setup-stepper" aria-label="Setup workflow steps">
              {workflowNavItems.map((item, index) => {
                const state = setupStepState(index);
                const statusLabel = state === "completed" ? "Completed" : state === "active" ? "Current" : "Upcoming";

                return (
                  <li key={item.path} className={`setup-stepper-item setup-stepper-item--${state}`}>
                    <NavLink
                      to={item.path}
                      className={({ isActive }) =>
                        `setup-step setup-step--${state}${isActive ? " setup-step--active" : ""}`
                      }
                      onClick={closeDrawer}
                      aria-label={`${workflowStepLabels[index]} ${item.label}, ${statusLabel}`}
                    >
                      <span className="setup-step-node" aria-hidden="true">
                        {state === "completed" ? <span className="setup-step-check" /> : workflowStepLabels[index]}
                      </span>
                      <span className="setup-step-copy">
                        <span className="setup-step-title">{item.label}</span>
                        <span className="setup-step-status">{statusLabel}</span>
                      </span>
                    </NavLink>
                  </li>
                );
              })}
            </ol>
          </section>

          <section className="nav-group" aria-labelledby="monitor-nav-heading">
            <h2 id="monitor-nav-heading">Execution</h2>
            <NavLink to={monitorNavItem.path} className={navLinkClass} onClick={closeDrawer}>
              <span className="nav-icon" aria-hidden="true">EX</span>
              <span>{monitorNavItem.label}</span>
            </NavLink>
          </section>

          <section className="nav-group" aria-labelledby="results-nav-heading">
            <h2 id="results-nav-heading">Results</h2>
            {resultNavItems.map((item) => (
              <NavLink key={item.path} to={resultPath(item.path)} className={navLinkClass} end={item.path === "/results/history"} onClick={closeDrawer}>
                <span className="nav-icon" aria-hidden="true">RS</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </section>

        </nav>
      </aside>
      {isDrawerOpen ? <button className="drawer-scrim" type="button" aria-label="Close navigation" onClick={closeDrawer} /> : null}

      <div className="workspace">
        <header className="topbar">
          <button
            className="menu-button"
            type="button"
            aria-label={isDrawerOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={isDrawerOpen}
            onClick={() => setIsDrawerOpen((open) => !open)}
          >
            <span aria-hidden="true" />
          </button>
          <div className="topbar-brand">
            <img className="topbar-brand-mark" src={blueAlphaLogo} alt="BlueAlpha" />
            <div className="topbar-product-title">Bayesian MMM Prior Sensitivity Dashboard</div>
          </div>
          <div className="topbar-team" aria-label="Project team">
            <span>Jasper Luo</span>
            <span>Quinlan Wilson</span>
            <span>Aidan Frazier</span>
            <span>Jimmy Wu</span>
            <span>Coraline Zhu</span>
          </div>
          <button className="help-button" type="button" aria-label="Open contextual help" aria-expanded={isHelpOpen} onClick={() => openContextualHelp()}>
            ?
          </button>
        </header>
        <main className="page-frame">
          <Outlet />
        </main>
      </div>
      <ContextualHelpDrawer open={isHelpOpen} initialSectionId={activeHelpSection} onClose={closeHelp} />
    </div>
  );
}
