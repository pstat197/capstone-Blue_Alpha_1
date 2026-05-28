import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

export type HelpSectionId =
  | "overview-reading"
  | "page-key-terms"
  | "low-confidence"
  | "qc-pass-rate"
  | "interpretation-tier"
  | "movement-chart"
  | "caution-flags"
  | "prior-posterior-chart"
  | "prior-mean"
  | "posterior-mean"
  | "posterior-interval"
  | "roi-reference"
  | "prior-sensitivity"
  | "interpretation-confidence"
  | "tornado-chart"
  | "movement-direction"
  | "max-shift"
  | "sensitivity-ranking"
  | "qc-status"
  | "qc-checks"
  | "primary-review-checks"
  | "warnings";

type HelpSection = {
  id: HelpSectionId;
  title: string;
  body: string;
  bullets?: string[];
};

type HelpContext = {
  eyebrow: string;
  title: string;
  intro: string;
  sections: HelpSection[];
};

const overviewContext: HelpContext = {
  eyebrow: "Overview Help",
  title: "Help for this overview",
  intro: "A quick read on run health, confidence, and where prior assumptions move results.",
  sections: [
    {
      id: "overview-reading",
      title: "How to read this page",
      body: "Use the top metrics to confirm the run set, then read the movement and diagnostic cards as confidence signals.",
      bullets: [
        "QC Pass Rate tells you how many completed runs cleared diagnostics.",
        "Diagnostic Interpretation tells you how cautious to be.",
        "Movement by Channel shows where prior assumptions matter most.",
      ],
    },
    {
      id: "qc-pass-rate",
      title: "QC pass rate",
      body: "The share of completed runs that passed diagnostic checks. A lower pass rate does not automatically invalidate the dashboard, but it should lower confidence.",
    },
    {
      id: "interpretation-tier",
      title: "Interpretation tier",
      body: "PASS supports normal interpretation. REVIEW means use the result directionally. FAIL means the affected output did not clear required quality gates.",
    },
    {
      id: "movement-chart",
      title: "Movement chart",
      body: "Ranks channel self-response movement across tested prior settings. Bigger movement means the conclusion depends more on prior choice.",
    },
    {
      id: "caution-flags",
      title: "Caution flags",
      body: "Flags name the specific issue limiting confidence, such as diagnostic review items or high prior sensitivity. Use them to decide where to inspect next.",
    },
  ],
};

const priorPosteriorContext: HelpContext = {
  eyebrow: "Prior vs Posterior Help",
  title: "Help for this chart",
  intro: "Use this page to see how much the data changed each channel's ROI prior.",
  sections: [
    {
      id: "prior-posterior-chart",
      title: "How to read this chart",
      body: "Each row is a channel. The markers show prior assumptions and posterior ROI estimates under different prior variants.",
      bullets: [
        "Colored dots are posterior means.",
        "Colored lines are 50% posterior intervals.",
        "Gray diamonds are prior means.",
        "The dashed ROI 1.0 line is the break-even reference.",
      ],
    },
    {
      id: "prior-mean",
      title: "Prior mean",
      body: "Prior mean is the expected ROI before fitting. It encodes the analyst's starting assumption for the media channel.",
    },
    {
      id: "posterior-mean",
      title: "Posterior mean dots",
      body: "A dot is the fitted ROI estimate after the model combines the prior assumption with observed data. Large dot movement across variants means the result is prior-sensitive.",
    },
    {
      id: "posterior-interval",
      title: "50% posterior intervals",
      body: "The horizontal line around each dot is the central 50% of plausible posterior ROI values. Wider lines mean more uncertainty.",
    },
    {
      id: "roi-reference",
      title: "ROI 1.0 dashed line",
      body: "ROI 1.0 is the break-even reference. Points to the right are above break-even; points to the left are below it.",
    },
    {
      id: "prior-sensitivity",
      title: "Prior sensitivity",
      body: "High sensitivity risk means posterior estimates change materially across tested prior settings. Treat those channels as more dependent on prior choice.",
    },
    {
      id: "interpretation-confidence",
      title: "Interpretation confidence",
      body: "A practical confidence read based on diagnostics and prior update behavior. Low confidence means use results directionally and inspect diagnostics before budget decisions.",
    },
  ],
};

const priorSensitivityContext: HelpContext = {
  eyebrow: "Prior Sensitivity Help",
  title: "Help for prior sensitivity",
  intro: "Use this page to see which channels move most when one target channel's prior changes.",
  sections: [
    {
      id: "tornado-chart",
      title: "Tornado-style movement",
      body: "The movement chart is read like a tornado chart: longer bars or larger shifts mean the channel is more sensitive to prior assumptions.",
    },
    {
      id: "movement-direction",
      title: "Positive and negative movement",
      body: "Positive movement means the channel estimate increased versus baseline under the tested prior changes. Negative movement means it decreased. Direction matters less than size when judging sensitivity.",
    },
    {
      id: "max-shift",
      title: "Max shift",
      body: "Max shift is the largest movement observed across tested prior settings. Use it as a worst-case sensitivity signal.",
    },
    {
      id: "sensitivity-ranking",
      title: "Channel ranking",
      body: "The ranking sorts channels by absolute movement. The top rows are the places where conclusions depend most on prior choice.",
    },
    {
      id: "prior-sensitivity",
      title: "What prior sensitivity means",
      body: "Prior sensitivity compares completed model outputs across a fixed grid of ROI prior assumptions. Large movement means the conclusion changes materially when the prior changes.",
    },
  ],
};

const auditContext: HelpContext = {
  eyebrow: "Audit Help",
  title: "Help for diagnostics",
  intro: "Use this page to decide whether results are ready to interpret or need follow-up.",
  sections: [
    {
      id: "qc-status",
      title: "PASS, REVIEW, and FAIL",
      body: "PASS indicates the run met diagnostic checks. REVIEW means the output is directional and should be interpreted cautiously. FAIL means the run or metric did not clear required quality gates.",
    },
    {
      id: "primary-review-checks",
      title: "Primary review checks",
      body: "The primary review check is the diagnostic most responsible for follow-up. Start there before inspecting lower-priority warnings.",
    },
    {
      id: "qc-checks",
      title: "QC check table",
      body: "The table shows each diagnostic, its status, why it matters, and the recommended follow-up. Focus on REVIEW and FAIL rows first.",
    },
    {
      id: "warnings",
      title: "How to interpret warnings",
      body: "Warnings do not automatically invalidate every chart. They identify the specific diagnostic or sensitivity issue that should limit how strongly you use the result.",
    },
    {
      id: "interpretation-tier",
      title: "Budget interpretation",
      body: "When diagnostics or prior sensitivity are elevated, use results directionally and review the affected checks before making budget-level decisions.",
    },
  ],
};

const defaultContext: HelpContext = {
  eyebrow: "Dashboard Help",
  title: "Help for this page",
  intro: "Short guidance for the current dashboard page.",
  sections: [
    {
      id: "overview-reading",
      title: "How to read this page",
      body: "Start with the page title and top summary metrics, then inspect any charts or tables that explain the main signal.",
    },
    {
      id: "page-key-terms",
      title: "Key terms on this page",
      body: "ROI prior is the starting assumption. Posterior is the fitted estimate after seeing data. Prior sensitivity is how much conclusions change when priors change.",
    },
    {
      id: "low-confidence",
      title: "What to do if confidence is low",
      body: "Treat results directionally, inspect diagnostics and sensitivity rankings, then rerun with cleaner inputs or adjusted prior assumptions if needed.",
    },
  ],
};

export const documentationTopics = [
  "How to Read the Dashboard",
  "What Prior Sensitivity Means",
  "ROI Prior and Revenue-Equivalent ROI",
  "PASS, REVIEW, and FAIL",
  "How to Read Tornado Charts",
  "Why Post-Run Results Are Read-Only",
  "Data Requirements",
];

export const documentationFlow = [
  "Overview",
  "Prior Sensitivity",
  "Prior vs Posterior",
  "Scenario Explorer",
  "Model Structure",
  "Audit Diagnostics",
];

export const documentationReferenceSections = [
  {
    title: "ROI Prior and Revenue-Equivalent ROI",
    body: "ROI prior encodes the expected relationship between media spend and business response before fitting. For non-revenue KPIs, revenue-equivalent ROI converts the KPI into an estimated dollar value using the saved workflow assumption.",
  },
  {
    title: "PASS, REVIEW, and FAIL",
    body: auditContext.sections[0].body,
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

export function helpContextForPath(pathname: string): HelpContext {
  if (pathname.includes("/results/prior-vs-posterior")) return priorPosteriorContext;
  if (pathname.includes("/results/prior-sensitivity")) return priorSensitivityContext;
  if (pathname.includes("/results/run-audit-diagnostics")) return auditContext;
  if (pathname.includes("/results/overview")) return overviewContext;
  return defaultContext;
}

export function openContextualHelp(sectionId?: HelpSectionId) {
  window.dispatchEvent(new CustomEvent("bluealpha:open-help", { detail: { sectionId } }));
}

export function ContextualHelpButton({
  sectionId,
  label = "Open contextual help",
}: {
  sectionId: HelpSectionId;
  label?: string;
}) {
  return (
    <button className="context-help-trigger" type="button" aria-label={label} title={label} onClick={() => openContextualHelp(sectionId)}>
      i
    </button>
  );
}

export function ContextualHelpDrawer({
  open,
  initialSectionId,
  onClose,
}: {
  open: boolean;
  initialSectionId?: HelpSectionId | null;
  onClose: () => void;
}) {
  const location = useLocation();
  const [openSectionId, setOpenSectionId] = useState<HelpSectionId | undefined>();
  const context = helpContextForPath(location.pathname);
  const activeSectionId = initialSectionId && context.sections.some((section) => section.id === initialSectionId)
    ? initialSectionId
    : context.sections[0]?.id;
  const orderedSections = activeSectionId
    ? [
        ...context.sections.filter((section) => section.id === activeSectionId),
        ...context.sections.filter((section) => section.id !== activeSectionId),
      ]
    : context.sections;

  useEffect(() => {
    if (open) {
      setOpenSectionId(activeSectionId);
    }
  }, [activeSectionId, open, location.pathname]);

  return (
    <>
      {open ? <button className="help-drawer-scrim" type="button" aria-label="Close help" onClick={onClose} /> : null}
      <aside className={open ? "help-drawer help-drawer--open" : "help-drawer"} aria-hidden={!open} aria-label="Contextual help">
        <header className="help-drawer-header">
          <div>
            <span className="eyebrow">{context.eyebrow}</span>
            <h2>{context.title}</h2>
          </div>
          <button className="help-drawer-close" type="button" aria-label="Close help" onClick={onClose}>
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <p className="help-drawer-intro">{context.intro}</p>
        <div className="help-drawer-section-list" key={`${location.pathname}-${activeSectionId || "default"}`}>
          {orderedSections.map((section) => (
            <section
              className={section.id === activeSectionId ? "help-drawer-section help-drawer-section--active" : "help-drawer-section"}
              id={`help-${section.id}`}
              key={section.id}
            >
              <button
                className="help-drawer-section-toggle"
                type="button"
                aria-expanded={openSectionId === section.id}
                aria-controls={`help-panel-${section.id}`}
                onClick={() => setOpenSectionId((current) => current === section.id ? undefined : section.id)}
              >
                <span>{section.title}</span>
                <i aria-hidden="true" />
              </button>
              {openSectionId === section.id ? (
                <div className="help-drawer-section-body" id={`help-panel-${section.id}`}>
                  <p>{section.body}</p>
                  {section.bullets ? (
                    <ul>
                      {section.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </section>
          ))}
        </div>
        <footer className="help-drawer-footer">
          <Link to="/help" onClick={onClose}>Open full reference</Link>
        </footer>
      </aside>
    </>
  );
}
