const quickTopics = [
  "How to Read the Dashboard",
  "What Prior Sensitivity Means",
  "ROI Prior and Revenue-Equivalent ROI",
  "PASS, REVIEW, and FAIL",
  "How to Read Tornado Charts",
  "Why Post-Run Results Are Read-Only",
  "Data Requirements",
];

const dashboardFlow = [
  "Overview",
  "Prior Sensitivity",
  "Prior vs Posterior",
  "Scenario Explorer",
  "Model Structure",
  "Audit Diagnostics",
];

const referenceSections = [
  {
    title: "ROI Prior and Revenue-Equivalent ROI",
    body: "ROI prior encodes the expected relationship between media spend and business response before fitting. For non-revenue KPIs, revenue-equivalent ROI converts the KPI into an estimated dollar value using the saved workflow assumption.",
  },
  {
    title: "PASS, REVIEW, and FAIL",
    body: "PASS indicates the run met the dashboard's diagnostic checks. REVIEW means the output is directional and should be interpreted cautiously. FAIL means the run or metric did not clear required quality gates.",
  },
  {
    title: "How to Read Tornado Charts",
    body: "Tornado charts rank channels by movement across prior assumptions. Longer bars indicate larger sensitivity. Use them to find where conclusions depend most on prior choice.",
  },
  {
    title: "Why Post-Run Results Are Read-Only",
    body: "Results pages show generated artifacts from a completed backend run. Editing model configuration happens only in the setup workflow before launching a new run.",
  },
  {
    title: "Data Requirements",
    body: "The expected CSV includes a date column, KPI column, media activity or spend columns by channel, and optional revenue, control, geo, and population fields. The Upload Data step validates and profiles the file before configuration.",
  },
];

export function DocumentationPage() {
  return (
    <article className="documentation-page">
      <div className="page-heading">
        <div className="page-heading-copy">
          <span className="eyebrow">HELP</span>
          <h2>Help / Documentation</h2>
          <p className="page-summary">
            Lightweight methodology notes for reading completed prior-sensitivity results. Model configuration belongs in the setup workflow.
          </p>
        </div>
        <span className="mode-chip mode-chip--pre-run">reference</span>
      </div>

      <div className="documentation-layout">
        <aside className="documentation-topics content-panel" aria-label="Quick documentation topics">
          <h3>Quick Topics</h3>
          <nav className="documentation-topic-list">
            {quickTopics.map((topic, index) => (
              <a
                className={index === 0 ? "documentation-topic documentation-topic--active" : "documentation-topic"}
                href={`#${topic.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`}
                key={topic}
              >
                <span className="documentation-topic-icon" aria-hidden="true" />
                <span>{topic}</span>
              </a>
            ))}
          </nav>
          <div className="documentation-help-box">
            <strong>Need more help?</strong>
            <span>Contact your BlueAlpha team for assistance.</span>
          </div>
        </aside>

        <section className="documentation-content" aria-label="Dashboard documentation">
          <div className="documentation-feature-grid">
            <article className="content-panel documentation-card documentation-card--feature" id="how-to-read-the-dashboard">
              <span className="documentation-card-icon documentation-card-icon--dashboard" aria-hidden="true" />
              <h3>How to Read the Dashboard</h3>
              <p>
                Start with Results / Overview for run health, modeled scope, and movement signals, then move through the
                completed result views in order.
              </p>
              <div className="documentation-flow" aria-label="Recommended dashboard reading order">
                {dashboardFlow.map((item, index) => (
                  <div className="documentation-flow-step" key={item}>
                    <span>{item.split(" ").map((word) => word[0]).join("")}</span>
                    <small>{item}</small>
                    {index < dashboardFlow.length - 1 ? <b aria-hidden="true" /> : null}
                  </div>
                ))}
              </div>
            </article>

            <article className="content-panel documentation-card documentation-card--feature" id="what-prior-sensitivity-means">
              <span className="documentation-card-icon documentation-card-icon--sensitivity" aria-hidden="true" />
              <h3>What Prior Sensitivity Means</h3>
              <p>Prior sensitivity compares completed model outputs across a fixed grid of ROI prior assumptions.</p>
              <div className="documentation-callout">
                Large movement means the result changes materially when the prior changes, so conclusions depend more on
                prior choice.
              </div>
            </article>
          </div>

          <div className="documentation-grid">
            {referenceSections.map((section) => (
              <article
                className="content-panel documentation-card documentation-card--compact"
                id={section.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}
                key={section.title}
              >
                <span className="documentation-card-icon" aria-hidden="true" />
                <h3>{section.title}</h3>
                <p>{section.body}</p>
              </article>
            ))}
          </div>
        </section>
      </div>
    </article>
  );
}
