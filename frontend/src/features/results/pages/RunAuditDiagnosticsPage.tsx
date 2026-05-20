import type { CSSProperties } from "react";
import { SectionScaffold } from "../components/SectionScaffold";
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

function overallHealth(payload: DashboardPayload, overview: DashboardPayload["diagnostics_overview"]) {
  const decision = payload.decision_card || {};
  const score = asNumber(decision.score_numeric) ?? asNumber(String(decision.score_value || "").match(/[-+]?\d*\.?\d+/)?.[0]);
  const status =
    normalizeStatus(decision.tier_class) !== "UNAVAILABLE"
      ? normalizeStatus(decision.tier_class)
      : normalizeStatus(decision.tier) !== "UNAVAILABLE"
        ? normalizeStatus(decision.tier)
        : (asNumber(overview?.fail_runs) || 0) > 0
          ? "FAIL"
          : (asNumber(overview?.review_runs) || 0) > 0
            ? "REVIEW"
            : (asNumber(overview?.pass_runs) || 0) > 0
              ? "PASS"
              : "UNAVAILABLE";
  return { score, status };
}

function guidanceFor(rows: DiagnosticCheckRow[], primaryCheck: string): Array<{ title: string; body: string; tone: string }> {
  const issueNames = new Set(rows.filter((row) => statusForCheck(row) !== "PASS").map((row) => displayCheckName(row.check)));
  if (primaryCheck !== "NA") issueNames.add(primaryCheck);
  if (!issueNames.size) {
    return [{ title: "Diagnostics support interpretation.", body: "No review or fail checks are present in the selected run diagnostics.", tone: "pass" }];
  }

  const items: Array<{ title: string; body: string; tone: string }> = [
    {
      title: "Resolve review runs before stronger conclusions.",
      body: primaryCheck !== "NA" ? `Address ${primaryCheck} items and complete follow-up runs as needed.` : "Address review items before stronger interpretation.",
      tone: "review",
    },
  ];
  if (issueNames.has("PriorPosteriorShift")) {
    items.push({
      title: "Inspect prior-posterior shift.",
      body: "Review channels with large or minimal posterior shift according to the selected run diagnostic definition.",
      tone: "info",
    });
  }
  if (issueNames.has("ROIConsistency")) {
    items.push({
      title: "Check ROI prior alignment.",
      body: "Compare ROI posterior behavior with the custom priors before stronger ROI interpretation.",
      tone: "review",
    });
  }
  if (issueNames.has("Convergence")) {
    items.push({
      title: "Inspect sampler diagnostics.",
      body: "Review convergence evidence before relying on affected run outputs.",
      tone: "fail",
    });
  }
  if (issueNames.has("GoodnessOfFit")) {
    items.push({
      title: "Inspect model fit.",
      body: "Use fit diagnostics to identify where the selected run needs model review.",
      tone: "review",
    });
  }
  if (issueNames.has("Baseline")) {
    items.push({
      title: "Verify baseline-sensitive channels.",
      body: "Visually inspect baseline fits and confirm no baseline risks are driving interpretation.",
      tone: "purple",
    });
  }
  return items;
}

export function RunAuditDiagnosticsPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const diagnostics = selectDiagnostics(payload);
  const overview = diagnostics.overview || payload.diagnostics_overview || {};
  const checkRows = diagnostics.check_rows || [];
  const primary = primaryReview(payload, checkRows);
  const health = overallHealth(payload, overview);
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
  const guidance = guidanceFor(checkRows, hasIssue ? primary.check : "NA");
  const contextStatus = fail > 0 || review > 0 || health.status === "FAIL" || health.status === "REVIEW"
    ? "Requires further testing"
    : health.status === "PASS"
      ? "Ready for interpretation"
      : "Unavailable";

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
              <p>{payload.decision_card?.headline || "Health explanation unavailable."}</p>
            </div>
          </article>
          <article className="audit-summary-card audit-summary-card--wide">
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
          <article className="audit-summary-card">
            <div>
              <span>Primary Review Check</span>
              <strong>{primary.check}</strong>
              <p>{primary.count === null ? "Follow-up count unavailable." : `${displayNumber(primary.count)} runs need follow-up for this check.`}</p>
            </div>
          </article>
        </section>

        <section className="audit-main-grid">
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
            <p>{payload.decision_card?.headline || "Model health score is unavailable in the selected run payload."}</p>
          </article>

          <article className="audit-card audit-check-card">
            <h3>Check Status & Recommendation</h3>
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
                  {checkRows.length ? (
                    checkRows.map((row) => {
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

        <section className="audit-bottom-grid">
          <article className="audit-card audit-context-card">
            <h3>Diagnostic Context</h3>
            <div className="audit-context-layout">
              <div
                className="audit-mix-donut"
                style={{
                  "--pass-pct": `${passPct}%`,
                  "--review-pct": `${reviewPct}%`,
                  "--fail-pct": `${failPct}%`,
                } as CSSProperties}
              >
                <div>
                  <strong>{displayNumber(totalRuns)}</strong>
                  <span>runs</span>
                </div>
              </div>
              <div className="audit-context-stack">
                <div className="audit-mini-card">
                  <span>PASS / REVIEW / FAIL</span>
                  <strong>{displayNumber(pass)} / {displayNumber(review)} / {displayNumber(fail)}</strong>
                  <p>Completed-run diagnostics</p>
                </div>
                <div className="audit-mini-card">
                  <span>Good Enough To Interpret?</span>
                  <strong className={`audit-pill audit-pill--${contextStatus === "Ready for interpretation" ? "pass" : contextStatus === "Unavailable" ? "unavailable" : "review"}`}>
                    {contextStatus}
                  </strong>
                </div>
                <div className="audit-mini-card">
                  <span>Primary Review Check</span>
                  <strong>{primary.check}</strong>
                  <p>{primary.count === null ? "Follow-up count unavailable." : `${displayNumber(primary.count)} runs need follow-up for this check.`}</p>
                </div>
              </div>
            </div>
            <p className="audit-context-note">
              {contextStatus === "Ready for interpretation" ? "Diagnostics support interpretation for the selected run." : "Directional only: resolve QC or stability risks before stronger interpretation."}
            </p>
          </article>

          <article className="audit-card audit-guidance-card">
            <h3>Actionable Guidance</h3>
            <div className="audit-guidance-list">
              {guidance.map((item) => (
                <div className="audit-guidance-item" key={item.title}>
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </article>
        </section>
      </div>
    </SectionScaffold>
  );
}
