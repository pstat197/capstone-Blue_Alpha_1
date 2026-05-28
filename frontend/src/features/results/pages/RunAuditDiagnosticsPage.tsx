import type { CSSProperties } from "react";
import { SectionScaffold } from "../components/SectionScaffold";
import { ContextualHelpButton } from "../../../shared/ContextualHelp";
import { useCurrentResult } from "../data/resultLoader";
import type { DashboardPayload, DiagnosticCheckRow } from "../data/resultTypes";

type DiagnosticStatus = "PASS" | "REVIEW" | "FAIL" | "UNAVAILABLE";

function asNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function displayNumber(value: unknown, digits = 0): string {
  const n = asNumber(value);
  if (n === null) return "NA";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(n);
}

function displayPercent(value: unknown): string {
  const n = asNumber(value);
  return n === null ? "NA" : `${displayNumber(n, 1)}%`;
}

function normalizeStatus(value: unknown): DiagnosticStatus {
  const raw = String(value || "").trim().toUpperCase();
  if (raw === "GREEN" || raw === "PASS" || raw === "PASSED") return "PASS";
  if (raw === "YELLOW" || raw === "AMBER" || raw === "REVIEW" || raw === "WARNING") return "REVIEW";
  if (raw === "RED" || raw === "FAIL" || raw === "FAILED") return "FAIL";
  return "UNAVAILABLE";
}

function displayCheckName(check: unknown): string {
  const raw = String(check || "").trim();
  if (!raw) return "Unavailable";
  const normalized = raw.toLowerCase().replace(/[\s-]+/g, "_");
  const known: Record<string, string> = {
    bayesianppp: "BayesianPPP",
    bayesian_ppp: "BayesianPPP",
    gof: "GoodnessOfFit",
    goodness_of_fit: "GoodnessOfFit",
    prior_posterior_shift: "PriorPosteriorShift",
    posterior_prior_shift: "PriorPosteriorShift",
    roi_consistency: "ROIConsistency",
  };
  if (known[normalized]) return known[normalized];
  return raw
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

function statusForCheck(row: DiagnosticCheckRow): DiagnosticStatus {
  const fail = asNumber(row.fail_count) || 0;
  const review = asNumber(row.review_count) || 0;
  const pass = asNumber(row.pass_count) || 0;
  if (fail > 0) return "FAIL";
  if (review > 0) return "REVIEW";
  if (pass > 0) return "PASS";
  return "UNAVAILABLE";
}

function checkFollowupCount(row: DiagnosticCheckRow): number {
  return (asNumber(row.review_count) || 0) + (asNumber(row.fail_count) || 0);
}

function fallbackRecommendation(checkName: string, status: DiagnosticStatus): string {
  if (status === "PASS") return `${checkName} passed in the selected run diagnostics.`;
  if (status === "UNAVAILABLE") return `${checkName} diagnostics are unavailable in the selected run payload.`;
  if (checkName === "PriorPosteriorShift") return "Review channels where posterior movement requires follow-up before stronger interpretation.";
  if (checkName === "ROIConsistency") return "Review ROI prior alignment before using stronger ROI conclusions.";
  if (checkName === "Convergence") return "Inspect sampler and convergence diagnostics before interpreting affected runs.";
  if (checkName === "GoodnessOfFit") return "Inspect model fit diagnostics before relying on stronger conclusions.";
  if (checkName === "Baseline") return "Inspect baseline-sensitive channels before stronger interpretation.";
  return `Review ${checkName} diagnostics before stronger interpretation.`;
}

function checkMeaning(checkName: string, status: DiagnosticStatus): string {
  const needsCaution = status === "FAIL" || status === "REVIEW";
  if (checkName === "Convergence") {
    return needsCaution
      ? "Whether sampling is stable; review means posterior estimates may need cautious interpretation."
      : "Whether the sampler appears stable and posterior estimates are reliable enough to interpret.";
  }
  if (checkName === "Baseline") {
    return needsCaution
      ? "Whether the non-media baseline behaves reasonably; review can signal baseline attribution risk."
      : "Whether the baseline / non-media component behaves reasonably in the selected diagnostics.";
  }
  if (checkName === "BayesianPPP") {
    return needsCaution
      ? "Posterior predictive check; review can mean simulated outcomes do not resemble observed KPI patterns."
      : "Posterior predictive check: whether simulated outcomes resemble the observed data.";
  }
  if (checkName === "GoodnessOfFit") {
    return needsCaution
      ? "Whether model fit is acceptable; review can make channel-level interpretation less trustworthy."
      : "Whether the fitted model explains the observed KPI pattern with acceptable accuracy.";
  }
  if (checkName === "PriorPosteriorShift") {
    return needsCaution
      ? "Whether posterior estimates moved meaningfully from the prior; review flags prior influence or instability."
      : "Whether posterior estimates moved meaningfully from the prior, showing how data updated assumptions.";
  }
  if (checkName === "ROIConsistency") {
    return needsCaution
      ? "Whether ROI outputs are stable and internally consistent; review weakens strong budget interpretation."
      : "Whether ROI-related outputs are stable and internally consistent across selected diagnostics.";
  }
  return needsCaution
    ? "Diagnostic review item from the selected run payload; interpret affected outputs cautiously."
    : "Diagnostic check from the selected run payload.";
}

function issueDescription(checkName: string): string {
  if (checkName === "PriorPosteriorShift") {
    return "PriorPosteriorShift means the posterior moved substantially away from the prior or did not shift enough under this diagnostic definition, so this run needs follow-up review before stronger interpretation.";
  }
  if (checkName === "ROIConsistency") return "ROIConsistency is the primary review check, so ROI prior alignment needs follow-up before stronger interpretation.";
  if (checkName === "Convergence") return "Convergence is the primary review check, so sampler diagnostics need follow-up before stronger interpretation.";
  if (checkName === "GoodnessOfFit") return "GoodnessOfFit is the primary review check, so model fit needs follow-up before stronger interpretation.";
  if (checkName === "Baseline") return "Baseline is the primary review check, so baseline-sensitive channels need follow-up before stronger interpretation.";
  return `${checkName} is the primary review check, so this run needs follow-up review before stronger interpretation.`;
}

function selectDiagnostics(payload: DashboardPayload) {
  return payload.diagnostics || { overview: payload.diagnostics_overview };
}

function primaryReview(payload: DashboardPayload, rows: DiagnosticCheckRow[]) {
  const primaryRows = payload.diagnostics?.primary_rows || [];
  const firstPrimary = primaryRows[0] || {};
  const qc = payload.qc_followup;
  const check = displayCheckName(qc?.primary_review_check || firstPrimary.check);
  const primaryRow = rows.find((row) => displayCheckName(row.check) === check);
  const count = asNumber(qc?.count) ?? asNumber(firstPrimary.count) ?? (primaryRow ? checkFollowupCount(primaryRow) : null);
  return {
    check: check === "Unavailable" ? "NA" : check,
    count,
  };
}

function diagnosticHealth(overview: DashboardPayload["diagnostics_overview"], rows: DiagnosticCheckRow[]) {
  let pass = asNumber(overview?.pass_runs);
  let review = asNumber(overview?.review_runs);
  let fail = asNumber(overview?.fail_runs);
  let unknown = asNumber(overview?.unknown_runs);

  if (pass === null && review === null && fail === null && unknown === null && rows.length) {
    pass = rows.reduce((sum, row) => sum + (asNumber(row.pass_count) || 0), 0);
    review = rows.reduce((sum, row) => sum + (asNumber(row.review_count) || 0), 0);
    fail = rows.reduce((sum, row) => sum + (asNumber(row.fail_count) || 0), 0);
    unknown = rows.reduce((sum, row) => sum + (asNumber(row.unknown_count) || 0), 0);
  }

  const passCount = pass || 0;
  const reviewCount = review || 0;
  const failCount = fail || 0;
  const unknownCount = unknown || 0;
  const total = passCount + reviewCount + failCount + unknownCount;
  const score = total > 0 ? (passCount / total) * 100 : null;
  const status: DiagnosticStatus =
    failCount > 0
      ? "FAIL"
      : reviewCount > 0 || unknownCount > 0
        ? "REVIEW"
        : passCount > 0
          ? "PASS"
          : "UNAVAILABLE";
  const summary =
    status === "PASS"
      ? "All completed runs and available diagnostic checks passed."
      : status === "FAIL"
        ? "One or more completed runs failed diagnostics."
        : status === "REVIEW"
          ? "One or more completed runs need diagnostic review."
          : "Diagnostic health is unavailable for the selected run payload.";
  return { score, status, summary };
}

function robustnessContext(payload: DashboardPayload, healthStatus: DiagnosticStatus, healthScore: number | null) {
  const decision = payload.decision_card || {};
  const score = asNumber(decision.score_numeric) ?? asNumber(String(decision.score_value || "").match(/[-+]?\d*\.?\d+/)?.[0]);
  const status =
    normalizeStatus(decision.tier_class) !== "UNAVAILABLE"
      ? normalizeStatus(decision.tier_class)
      : normalizeStatus(decision.tier);
  if (score === null || status === "UNAVAILABLE") return null;
  const differsFromDiagnostics = healthScore === null || Math.abs(score - healthScore) > 0.05 || status !== healthStatus;
  if (!differsFromDiagnostics) return null;
  const triggered = (decision.triggered_rules || []).find((rule) => String(rule || "").trim());
  return {
    score,
    status,
    label: decision.score_label || "Prior-Sensitivity Robustness",
    reason: triggered || decision.reasons?.find((reason) => String(reason || "").toLowerCase().includes("robustness")) || decision.headline || "",
  };
}

function robustnessReasonLines(reason: string) {
  const sensitivity = reason.match(/stable-baseline sensitivity\s+([-+]?\d*\.?\d+%)/i)?.[1];
  const threshold = reason.match(/threshold\s+([-+]?\d*\.?\d+%)/i)?.[1];
  return {
    sensitivityLine: `Largest stable-baseline sensitivity: ${sensitivity || "NA"}`,
    thresholdLine: `Review threshold: ${threshold || "15.0%"}`,
  };
}

function orderedCheckRows(rows: DiagnosticCheckRow[]): DiagnosticCheckRow[] {
  const order = ["Convergence", "Baseline", "BayesianPPP", "GoodnessOfFit", "PriorPosteriorShift", "ROIConsistency"];
  const byName = new Map(rows.map((row) => [displayCheckName(row.check), row]));
  const ordered = order.map((name) => byName.get(name) || { check: name });
  const extras = rows.filter((row) => !order.includes(displayCheckName(row.check)));
  return [...ordered, ...extras];
}

export function RunAuditDiagnosticsPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const diagnostics = selectDiagnostics(payload);
  const overview = diagnostics.overview || payload.diagnostics_overview || {};
  const checkRows = diagnostics.check_rows || [];
  const primary = primaryReview(payload, checkRows);
  const health = diagnosticHealth(overview, checkRows);
  const robustness = robustnessContext(payload, health.status, health.score);
  const pass = asNumber(overview.pass_runs) || 0;
  const review = asNumber(overview.review_runs) || 0;
  const fail = asNumber(overview.fail_runs) || 0;
  const unknown = asNumber(overview.unknown_runs) || 0;
  const completedRuns = asNumber(overview.n_runs);
  const totalRuns = pass + review + fail + unknown || completedRuns || 0;
  const hasIssue = primary.check !== "NA" && ((primary.count ?? 0) > 0 || review > 0 || fail > 0);
  const scorePct = health.score === null ? 0 : Math.max(0, Math.min(100, health.score));
  const passPct = totalRuns ? (pass / totalRuns) * 100 : 0;
  const reviewPct = totalRuns ? (review / totalRuns) * 100 : 0;
  const failPct = totalRuns ? (fail / totalRuns) * 100 : 0;
  const diagnosticRows = orderedCheckRows(checkRows);
  const robustnessLines = robustness ? robustnessReasonLines(robustness.reason) : null;

  return (
    <SectionScaffold
      title="Run Audit & Diagnostics"
      summary="Model health, review checks, and audit context for the completed runs."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
      activeRunId={result.activeRunId}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
      headerAside={null}
    >
      <div className="run-audit-dashboard">
        <section className={`audit-alert audit-alert--${hasIssue ? "review" : "pass"}`}>
          <span className="audit-alert__icon" aria-hidden="true" />
          <p>{hasIssue ? issueDescription(primary.check) : "All available diagnostic checks passed for the selected run payload."}</p>
        </section>

        <section className="audit-summary-grid" aria-label="Run audit summary">
          <article className="audit-summary-card">
            <div>
              <span>Completed Runs</span>
              <strong>{displayNumber(completedRuns)}</strong>
              <p>Generated {payload.meta?.generated_at || "NA"}</p>
            </div>
          </article>
          <article className="audit-summary-card">
            <div>
              <span>Overall Model Health</span>
              <strong>{health.score === null ? "NA" : `${displayNumber(health.score, 1)} / ${health.status}`}</strong>
              <p>{health.summary}</p>
            </div>
          </article>
          <article className="audit-summary-card audit-summary-card--wide audit-summary-card--with-help">
            <ContextualHelpButton sectionId="qc-status" label="Explain PASS, REVIEW, and FAIL" />
            <div>
              <span>QC Status Mix</span>
              <strong>PASS {displayNumber(pass)} / REVIEW {displayNumber(review)} / FAIL {displayNumber(fail)}</strong>
              <p>Completed-run diagnostics</p>
              <div className="audit-status-legend">
                <span><i className="status-dot status-dot--pass" />PASS {displayPercent(overview.pass_rate_pct ?? passPct)}</span>
                <span><i className="status-dot status-dot--review" />REVIEW {displayPercent(overview.review_rate_pct ?? reviewPct)}</span>
                <span><i className="status-dot status-dot--fail" />FAIL {displayPercent(overview.fail_rate_pct ?? failPct)}</span>
              </div>
            </div>
          </article>
          <article className="audit-summary-card audit-summary-card--with-help">
            <ContextualHelpButton sectionId="primary-review-checks" label="Explain primary review checks" />
            <div>
              <span>Primary Review Check</span>
              <strong>{primary.check}</strong>
              <p>{primary.count === null ? "Follow-up count unavailable." : `${displayNumber(primary.count)} runs need follow-up for this check.`}</p>
            </div>
          </article>
        </section>

        <section className="audit-main-grid">
          <div className="audit-left-column">
            <article className="audit-card audit-health-card">
              <h3>Model Health Score</h3>
              <div
                className={`audit-score-donut audit-score-donut--${health.status.toLowerCase()}`}
                style={{ "--score-pct": `${scorePct}%` } as CSSProperties}
              >
                <div>
                  <strong>{health.score === null ? "NA" : displayNumber(health.score, 1)}</strong>
                </div>
              </div>
              <span className={`audit-pill audit-pill--${health.status.toLowerCase()}`}>Overall: {health.status}</span>
              <p>{health.summary}</p>
            </article>

            {robustness ? (
              <article className="audit-card audit-robustness-card">
                <h3>Sensitivity Robustness Context</h3>
                <span className={`audit-pill audit-pill--${robustness.status.toLowerCase()}`}>{robustness.status}</span>
                <div className="audit-robustness-reason">
                  <strong>{robustnessLines?.sensitivityLine || "Largest stable-baseline sensitivity: NA"}</strong>
                  <strong>{robustnessLines?.thresholdLine || "Review threshold: 15.0%"}</strong>
                </div>
                <p>Diagnostics passed, but prior sensitivity is high. Interpret results directionally rather than as a strong budget recommendation.</p>
                <div className="audit-robustness-score">
                  <span>Robustness score: {displayNumber(robustness.score, 1)}/100</span>
                  <span>Separate from diagnostic health.</span>
                </div>
              </article>
            ) : null}
          </div>

          <article className="audit-card audit-check-card">
            <div className="section-title-row section-title-row--compact">
              <h3>Check Status & Recommendation</h3>
              <ContextualHelpButton sectionId="qc-checks" label="Explain QC checks" />
            </div>
            <div className="audit-table-wrap">
              <table className="audit-check-table">
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Status</th>
                    <th>Meaning / Why it matters</th>
                    <th>Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {diagnosticRows.length ? (
                    diagnosticRows.map((row) => {
                      const name = displayCheckName(row.check);
                      const status = statusForCheck(row);
                      return (
                        <tr key={String(row.check || name)}>
                          <td>{name}</td>
                          <td><span className={`audit-pill audit-pill--${status.toLowerCase()}`}>{status}</span></td>
                          <td>{checkMeaning(name, status)}</td>
                          <td>{row.recommendation || fallbackRecommendation(name, status)}</td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={4}>Diagnostic checks are unavailable in the selected run payload.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <section className="audit-card audit-actionable-card">
          <div className="audit-actionable-heading">
            <div className="inline-help-row">
              <h3>Actionable Guidance</h3>
              <ContextualHelpButton sectionId="warnings" label="Explain diagnostic warnings" />
            </div>
            <strong>Diagnostics support interpretation, but sensitivity robustness requires caution.</strong>
          </div>
          <div className="audit-actionable-list">
            <div className="audit-actionable-item audit-actionable-item--pass">
              <span aria-hidden="true" />
              <p>All completed runs passed diagnostic checks.</p>
            </div>
            <div className="audit-actionable-item audit-actionable-item--pass">
              <span aria-hidden="true" />
              <p>No review or fail checks are present in the diagnostic table.</p>
            </div>
            <div className="audit-actionable-item audit-actionable-item--review">
              <span aria-hidden="true" />
              <p>{robustnessLines ? `Stable-baseline sensitivity is high (${robustnessLines.sensitivityLine.replace("Largest stable-baseline sensitivity: ", "")} vs threshold ${robustnessLines.thresholdLine.replace("Review threshold: ", "")}).` : "Stable-baseline sensitivity may require prior review."}</p>
            </div>
            <div className="audit-actionable-item audit-actionable-item--pass">
              <span aria-hidden="true" />
              <p>Use results directionally and review prior sensitivity before making budget-level decisions.</p>
            </div>
          </div>
        </section>
      </div>
    </SectionScaffold>
  );
}
