import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import blueAlphaLogo from "../../assets/bluealpha_mark_blue.png";
import { monitorNavItem, resultNavItems, workflowNavItems } from "../navigation";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? "nav-link nav-link--active" : "nav-link";

const navIconLabels = ["01", "02", "03", "04", "05"];

export function AppShell() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const closeDrawer = () => setIsDrawerOpen(false);

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
            {workflowNavItems.map((item, index) => (
              <NavLink key={item.path} to={item.path} className={navLinkClass} onClick={closeDrawer}>
                <span className="nav-icon" aria-hidden="true">{navIconLabels[index]}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
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
              <NavLink key={item.path} to={item.path} className={navLinkClass} onClick={closeDrawer}>
                <span className="nav-icon" aria-hidden="true">RS</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </section>

          <section className="nav-group nav-group--utility" aria-labelledby="utility-nav-heading">
            <h2 id="utility-nav-heading">Settings / Documentation</h2>
            <div className="nav-link nav-link--static">
              <span className="nav-icon" aria-hidden="true">ST</span>
              <span>Settings</span>
            </div>
            <div className="nav-link nav-link--static">
              <span className="nav-icon" aria-hidden="true">DC</span>
              <span>Documentation</span>
            </div>
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
            <span>Jimmy Wu</span>
            <span>Aidan Frazier</span>
            <span>Coraline Zhu</span>
          </div>
          <button className="help-button" type="button" aria-label="Help">?</button>
        </header>
        <main className="page-frame">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
