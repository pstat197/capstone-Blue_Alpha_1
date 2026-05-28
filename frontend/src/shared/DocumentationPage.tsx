import { documentationFlow, documentationReferenceSections, documentationTopics } from "./ContextualHelp";

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
            {documentationTopics.map((topic, index) => (
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
                {documentationFlow.map((item, index) => (
                  <div className="documentation-flow-step" key={item}>
                    <span>{item.split(" ").map((word) => word[0]).join("")}</span>
                    <small>{item}</small>
                    {index < documentationFlow.length - 1 ? <b aria-hidden="true" /> : null}
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
            {documentationReferenceSections.map((section) => (
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
