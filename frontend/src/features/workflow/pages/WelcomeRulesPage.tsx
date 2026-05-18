import { NavLink } from "react-router-dom";
import { WorkflowScaffold } from "../components/WorkflowScaffold";

const exampleColumns = [
  "date",
  "subscriptions",
  "revenue_per_subscription",
  "meta_impressions",
  "meta_spend",
  "google_clicks",
  "google_spend",
  "tiktok_impressions",
  "tiktok_spend",
  "promo",
  "competitor_sales",
];

const exampleRows = [
  ["2024-01-01", "1,245", "42.50", "1,234,567", "12,345.67", "45,678", "8,765.43", "789,012", "6,543.21", "0.12", "98,765"],
  ["2024-01-08", "1,312", "41.80", "1,345,678", "13,210.11", "47,890", "9,012.34", "812,345", "6,987.65", "0.10", "101,234"],
  ["2024-01-15", "1,398", "43.10", "1,456,789", "13,987.65", "49,123", "9,543.21", "845,678", "7,234.56", "0.15", "103,456"],
];

const mappingPreview = [
  ["date", "time"],
  ["subscriptions", "kpi"],
  ["revenue_per_subscription", "revenue_per_kpi"],
  ["meta_impressions", "media: meta"],
  ["meta_spend", "media_spend: meta"],
  ["google_clicks", "media: google"],
  ["google_spend", "media_spend: google"],
  ["tiktok_impressions", "media: tiktok"],
  ["tiktok_spend", "media_spend: tiktok"],
  ["promo", "control"],
  ["competitor_sales", "control"],
];

const setupPreview = [
  ["Detect dataset structure", "Identify time, KPI, media, spend, and control candidates.", "data"],
  ["Map Meridian fields", "Pair channel activity with matching spend by channel.", "map"],
  ["Build prior grid", "Configure ROI prior means, sigma values, and run counts.", "grid"],
  ["Generate sensitivity dashboard", "Prepare the audit output for diagnostics and review.", "chart"],
];

const readinessChecks = [
  "Time column available",
  "KPI column available",
  "Media columns available",
  "Matching spend columns available",
  "Revenue per KPI or KPI type handled",
];

const exampleCsvHref = `data:text/csv;charset=utf-8,${encodeURIComponent(
  [exampleColumns.join(","), ...exampleRows.map((row) => row.map((value) => value.replaceAll(",", "")).join(","))].join("\n"),
)}`;

const meridianDataGuideHref = "https://developers.google.com/meridian/docs/user-guide/collect-data";
const pageTitle = "Start a Prior Sensitivity Audit";
const pageSummary = "Upload a Meridian-ready marketing dataset. We'll detect fields, suggest mappings, configure prior grids, and prepare the audit run.";

export function WelcomeRulesPage() {
  return (
    <WorkflowScaffold
      title={pageTitle}
      summary={pageSummary}
      primaryActionLabel="I understand — Continue to Upload"
      nextHelperText="Upload / Data Detection"
      hideStepper
      hidePageHeading
    >
      <section className="welcome-hero content-panel">
        <div className="welcome-hero-heading">
          <h2>{pageTitle}</h2>
          <p>{pageSummary}</p>
        </div>
        <div className="welcome-hero-copy">
          <span className="welcome-eyebrow">Meridian setup workflow</span>
          <div className="welcome-actions" aria-label="Welcome page actions">
            <NavLink className="welcome-action welcome-action--primary" to="/workflow/upload">
              Upload CSV
            </NavLink>
            <a className="welcome-action" href={exampleCsvHref} download="meridian_example.csv">
              Download example CSV
            </a>
            <a className="welcome-action" href={meridianDataGuideHref} rel="noreferrer" target="_blank">
              View Meridian data guide
            </a>
          </div>
        </div>
        <div className="welcome-hero-panel" aria-label="Meridian variable types">
          <div>
            <span>Required mapping types</span>
            <strong>time + kpi + media + spend</strong>
          </div>
          <div>
            <span>Non-revenue KPI support</span>
            <strong>revenue_per_kpi</strong>
          </div>
          <div>
            <span>Recommended context</span>
            <strong>controls</strong>
          </div>
        </div>
      </section>

      <section className="workflow-preview-section" aria-label="Workflow preview">
        <div className="workflow-preview-heading">
          <h3>What this workflow will do</h3>
          <p>A quick preview of the setup sequence before you upload data.</p>
        </div>
        <div className="audit-preview-grid">
          {setupPreview.map(([title, detail, icon]) => (
            <article className="audit-preview-card" key={title}>
              <span className={`audit-preview-icon audit-preview-icon--${icon}`} aria-hidden="true" />
              <div>
                <h3>{title}</h3>
                <p>{detail}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="welcome-main-grid">
        <div className="content-panel csv-example-panel">
          <div className="section-title-row">
            <div>
              <h3>Meridian-ready CSV example</h3>
              <p>Columns can use your naming convention as long as they map into Meridian variable types.</p>
            </div>
          </div>
          <div className="welcome-csv-layout">
            <div className="preview-table-shell welcome-table-shell">
              <table className="preview-table welcome-example-table">
                <thead>
                  <tr>
                    {exampleColumns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {exampleRows.map((row, rowIndex) => (
                    <tr key={`example-row-${rowIndex}`}>
                      {row.map((value, columnIndex) => (
                        <td key={`${exampleColumns[columnIndex]}-${rowIndex}`}>{value}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <aside className="mapping-preview-panel" aria-label="Auto-mapping preview">
              <h3>Auto-mapping preview</h3>
              <div className="mapping-preview-list">
                {mappingPreview.map(([source, target]) => (
                  <div className="mapping-preview-row" key={source}>
                    <strong>{source}</strong>
                    <span>{target}</span>
                  </div>
                ))}
              </div>
            </aside>
          </div>
        </div>

        <aside className="content-panel readiness-card">
          <h3>Meridian Readiness Checks</h3>
          <p>These checks will run after you upload your CSV.</p>
          <div className="readiness-list">
            {readinessChecks.map((check) => (
              <div className="readiness-item" key={check}>
                <span aria-hidden="true" />
                <strong>{check}</strong>
              </div>
            ))}
          </div>
          <div className="readiness-note">
            Pair media and spend by channel, for example meta_impressions with meta_spend.
          </div>
        </aside>
      </section>
    </WorkflowScaffold>
  );
}
