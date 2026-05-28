import { useState } from "react";
import { ArrowUpRight, BarChart3, BookOpen, CheckCircle2, Download, ExternalLink, FileDown, Info, ShieldCheck, Sparkles, Table2, UploadCloud, X } from "lucide-react";
import { NavLink } from "react-router-dom";
import { blankCsvTemplateUrl, runnableDemoCsvUrl, schemaPreviewCsvUrl } from "../../../api/uploads";
import { WorkflowScaffold } from "../components/WorkflowScaffold";
import "./WelcomeRulesPage.css";

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

const groupedMappingPreview = [
  {
    title: "Core fields",
    items: [
      "date -> time",
      "subscriptions -> kpi",
      "revenue_per_subscription -> revenue_per_kpi",
    ],
  },
  {
    title: "Media + spend pairs",
    items: [
      "meta_impressions + meta_spend -> media/spend: meta",
      "google_clicks + google_spend -> media/spend: google",
      "tiktok_impressions + tiktok_spend -> media/spend: tiktok",
    ],
  },
  {
    title: "Controls",
    items: [
      "promo -> control",
      "competitor_sales -> control",
    ],
  },
];

const meridianDataGuideHref = "https://developers.google.com/meridian/docs/user-guide/collect-data";
const pageTitle = "Start a Prior Sensitivity Audit";
const pageSummary = "Upload a Meridian-ready marketing dataset. We'll detect fields, suggest mappings, configure prior grids, and prepare the audit run.";

function SetupAtGlanceCard() {
  return (
    <aside className="start-card setup-glance-card" aria-label="Meridian setup at a glance">
      <div className="start-card-heading start-card-heading--inline">
        <span className="start-card-icon start-card-icon--book"><BookOpen size={20} /></span>
        <div>
          <h3>Meridian setup at a glance</h3>
          <p>We follow Meridian best practices for data structure and modeling.</p>
        </div>
      </div>
      <div className="setup-glance-list">
        {[
          ["Required fields", "time · kpi · media · spend"],
          ["Non-revenue KPI", "revenue_per_kpi"],
          ["Recommended context", "controls"],
        ].map(([label, value]) => (
          <div className="setup-glance-row" key={label}>
            <div className="setup-glance-label">
              <CheckCircle2 size={17} />
              <strong>{label}</strong>
            </div>
            <span>{value}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}

function UploadCard() {
  return (
    <section className="start-upload-card" aria-label="Upload your CSV">
      <div className="start-upload-main">
        <span className="start-upload-orb" aria-hidden="true"><UploadCloud size={42} /></span>
        <div className="start-upload-copy">
          <h3>Upload your CSV</h3>
          <p>Drag and drop on the upload step, or select a local CSV to profile your fields.</p>
          <span>CSV format up to 200MB</span>
        </div>
        <NavLink className="start-primary-button" to="/workflow/upload">
          <UploadCloud size={17} /> Select CSV
        </NavLink>
      </div>
      <div className="start-upload-note">
        <Info size={17} />
        <span>
          Not sure about the format? <a href={blankCsvTemplateUrl}>Download our template</a> or <a href={runnableDemoCsvUrl}>try the demo dataset</a>.
        </span>
      </div>
    </section>
  );
}

function QuickStartCards({ onPreview }: { onPreview: () => void }) {
  const cards = [
    {
      title: "CSV format preview",
      copy: "See a small example of the expected columns and auto-mapping behavior.",
      icon: <Table2 size={25} />,
      tone: "blue",
      bullets: ["3-row preview", "Auto-mapping example", "Good for understanding structure"],
      cta: "View preview",
      onClick: onPreview,
    },
    {
      title: "Download template",
      copy: "Get a blank CSV template with the recommended column structure.",
      icon: <FileDown size={25} />,
      tone: "green",
      bullets: ["Headers included", "Fill with your own data", "Ready for Meridian mapping"],
      cta: "Download template",
      href: blankCsvTemplateUrl,
    },
    {
      title: "Try runnable demo dataset",
      copy: "Use a realistic synthetic dataset to test the full workflow end-to-end.",
      icon: <Sparkles size={25} />,
      tone: "violet",
      bullets: ["3 years of weekly data", "Media, spend, KPI, and controls", "Designed to pass readiness checks"],
      cta: "Download demo CSV",
      href: runnableDemoCsvUrl,
      recommended: true,
    },
  ];

  return (
    <section className="start-card quick-start-panel" aria-label="Get started quickly">
      <div className="start-section-heading">
        <h3>Get started quickly</h3>
        <p>Choose an option below to explore the workflow.</p>
      </div>
      <div className="quick-start-grid">
        {cards.map((card, index) => (
          <article className={card.recommended ? "quick-start-card quick-start-card--recommended" : "quick-start-card"} key={card.title}>
            <div className={`quick-start-art quick-start-art--${card.tone}`}>
              <span>{card.icon}</span>
            </div>
            <div className="quick-start-copy">
              <div className="quick-start-title-row">
                <h4>{index + 1}. {card.title}</h4>
                {card.recommended ? <span>Recommended</span> : null}
              </div>
              <p>{card.copy}</p>
            </div>
            <ul className="quick-start-bullets">
              {card.bullets.map((bullet) => (
                <li key={bullet}><CheckCircle2 size={15} /> {bullet}</li>
              ))}
            </ul>
            {"onClick" in card ? (
              <button className="quick-start-cta" type="button" onClick={card.onClick}>
                {card.cta} <ArrowUpRight size={15} />
              </button>
            ) : (
              <a className={card.recommended ? "quick-start-cta quick-start-cta--primary" : "quick-start-cta"} href={card.href}>
                {card.cta} <Download size={15} />
              </a>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function ReadinessSummaryCard() {
  const groups = [
    {
      title: "Schema checks",
      copy: "Validate required columns and mappings.",
      icon: <ShieldCheck size={18} />,
      chips: ["Time", "KPI", "Media", "Spend", "Revenue per KPI / KPI type"],
      tone: "schema",
    },
    {
      title: "Modeling readiness checks",
      copy: "Assess data quality for reliable MMM.",
      icon: <BarChart3 size={18} />,
      chips: ["Sufficient history", "Weekly spacing", "No missing values", "Non-negative values", "Sufficient variation", "Low correlation risk", "Controls validity"],
      tone: "modeling",
    },
  ];

  return (
    <aside className="start-card readiness-summary-card" aria-label="Data readiness at a glance">
      <div className="start-section-heading">
        <h3>Data readiness at a glance</h3>
        <p>We'll check your file across two layers after upload.</p>
      </div>
      <div className="readiness-summary-groups">
        {groups.map((group, index) => (
          <section className="readiness-summary-group" key={group.title}>
            <div className={`readiness-summary-icon readiness-summary-icon--${group.tone}`}>{group.icon}</div>
            <div>
              <h4>{index + 1}. {group.title}</h4>
              <p>{group.copy}</p>
              <div className={`readiness-chip-list readiness-chip-list--${group.tone}`}>
                {group.chips.map((chip) => <span key={chip}>{chip}</span>)}
              </div>
            </div>
          </section>
        ))}
      </div>
      <div className="readiness-dynamic-note">
        <Info size={16} />
        <span>These checks are evaluated dynamically after upload. Results change based on the actual CSV.</span>
      </div>
    </aside>
  );
}

function SchemaPreviewModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="start-preview-modal-backdrop" role="presentation">
      <section className="start-preview-modal" role="dialog" aria-modal="true" aria-labelledby="csv-format-preview-title">
        <div className="start-section-heading schema-preview-heading">
          <div>
            <h3 id="csv-format-preview-title">CSV format preview</h3>
            <p>This tiny preview shows column structure and auto-mapping only. It is not large enough for Meridian modeling.</p>
          </div>
          <div className="start-preview-modal-actions">
            <a className="start-secondary-button" href={schemaPreviewCsvUrl}>
              <Download size={16} /> Download preview CSV
            </a>
            <button className="start-preview-close" type="button" aria-label="Close CSV preview" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="schema-preview-layout">
          <div className="preview-table-shell start-preview-table-shell">
            <table className="preview-table start-preview-table">
              <thead>
                <tr>
                  {exampleColumns.map((column) => <th key={column}>{column}</th>)}
                </tr>
              </thead>
              <tbody>
                {exampleRows.map((row, rowIndex) => (
                  <tr key={`example-row-${rowIndex}`}>
                    {row.map((value, columnIndex) => <td key={`${exampleColumns[columnIndex]}-${rowIndex}`}>{value}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mapping-chip-panel mapping-chip-panel--grouped">
            <h4>Auto-mapping preview</h4>
            <div className="mapping-group-list">
              {groupedMappingPreview.map((group) => (
                <section className="mapping-group" key={group.title}>
                  <h5>{group.title}</h5>
                  <div className="mapping-chip-list">
                    {group.items.map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function BestPracticeBanner() {
  return (
    <section className="start-best-practice-banner" aria-label="Data best practices">
      <span><Sparkles size={21} /></span>
      <div>
        <strong>Good data leads to reliable insights.</strong>
        <p>MMM is sensitive to data quality, especially length, variation, and correlation.</p>
      </div>
      <a href={meridianDataGuideHref} rel="noreferrer" target="_blank">
        See data best practices <ExternalLink size={16} />
      </a>
    </section>
  );
}

export function WelcomeRulesPage() {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  return (
    <WorkflowScaffold
      title={pageTitle}
      summary={pageSummary}
      primaryActionLabel="Continue to Upload"
      nextHelperText="Upload / Data Detection"
      hideStepper
      hidePageHeading
    >
      <div className="start-page">
        <section className="start-top-left">
          <div className="start-hero-copy" aria-label="Start page introduction">
            <h2>{pageTitle}</h2>
            <p>{pageSummary}</p>
          </div>

          <UploadCard />
        </section>

        <aside className="start-top-right" aria-label="Meridian setup guidance">
          <SetupAtGlanceCard />
        </aside>

        <section className="start-lower-grid" aria-label="Start page options and readiness">
          <QuickStartCards onPreview={() => setIsPreviewOpen(true)} />
          <ReadinessSummaryCard />
        </section>

        <BestPracticeBanner />
      </div>

      {isPreviewOpen ? <SchemaPreviewModal onClose={() => setIsPreviewOpen(false)} /> : null}
    </WorkflowScaffold>
  );
}
