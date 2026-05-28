import type { CSSProperties } from "react";
import { AlertTriangle, CheckCircle2, Crosshair, Info, ListChecks, ShieldCheck } from "lucide-react";
import { SectionScaffold } from "../components/SectionScaffold";
import { ContextualHelpButton } from "../../../shared/ContextualHelp";
import { useCurrentResult } from "../data/resultLoader";
import type {
  ConvergenceFailureRow,
  CoreModelHealth,
  DashboardPayload,
  DiagnosticCheckRow,
  PriorSensitivityAudit,
} from "../data/resultTypes";

type DiagnosticStatus = "PASS" | "REVIEW" | "FAIL" | "UNAVAILABLE";

const coreCheckOrder = ["Convergence", "Baseline", "BayesianPPP", "GoodnessOfFit", "ROIConsistency"];

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

function selectDiagnostics(payload: DashboardPayload) {
  return payload.diagnostics || { overview: payload.diagnostics_overview };
}

function orderedCoreRows(rows: DiagnosticCheckRow[]): DiagnosticCheckRow[] {
  const byName = new Map(rows.map((row) => [displayCheckName(row.check), row]));
  return coreCheckOrder.map((name) => byName.get(name) || { check: name });
}

function deriveCoreHealth(rows: DiagnosticCheckRow[], totalRuns: number): CoreModelHealth {
  const coreRows = orderedCoreRows(rows);
  let failedRuns = 0;
  let reviewRuns = 0;
  let unknownRuns = 0;
  coreRows.forEach((row) => {
    failedRuns = Math.max(failedRuns, asNumber(row.fail_count) || 0);
    reviewRuns = Math.max(reviewRuns, asNumber(row.review_count) || 0);
    unknownRuns = Math.max(unknownRuns, asNumber(row.unknown_count) || 0);
  });
  const passedRuns = Math.max(totalRuns - failedRuns - reviewRuns - unknownRuns, 0);
  return {
    available: coreRows.length > 0,
    total_runs: totalRuns,
    passed_runs: passedRuns,
    review_runs: reviewRuns,
    failed_runs: failedRuns,
    unknown_runs: unknownRuns,
    pass_rate_pct: totalRuns ? (passedRuns / totalRuns) * 100 : 0,
    excluded_checks: ["PriorPosteriorShift"],
    check_rows: coreRows,
  };
}

function derivePriorAudit(rows: DiagnosticCheckRow[], totalRuns: number): PriorSensitivityAudit {
  const pps = rows.find((row) => displayCheckName(row.check) === "PriorPosteriorShift");
  const convergence = rows.find((row) => displayCheckName(row.check) === "Convergence");
  const ppsReview = asNumber(pps?.review_count) || 0;
  return {
    available: Boolean(pps),
    total_runs: totalRuns,
    pps_any_channel_count: ppsReview,
    pps_review_runs: ppsReview,
    pps_pass_runs: asNumber(pps?.pass_count) || 0,
    pps_unknown_runs: asNumber(pps?.unknown_count) || 0,
    pps_review_rate_pct: totalRuns ? (ppsReview / totalRuns) * 100 : 0,
    target_breakdown_available: false,
    pps_convergence_fail_overlap_runs: Math.min(ppsReview, asNumber(convergence?.fail_count) || 0),
  };
}

function primaryReview(payload: DashboardPayload, rows: DiagnosticCheckRow[]) {
  const primaryRows = payload.diagnostics?.primary_rows || [];
  const firstPrimary = primaryRows[0] || {};
  const qc = payload.qc_followup;
  const check = displayCheckName(qc?.primary_review_check || firstPrimary.check);
  const primaryRow = rows.find((row) => displayCheckName(row.check) === check);
  const rowCount = primaryRow ? (asNumber(primaryRow.review_count) || 0) + (asNumber(primaryRow.fail_count) || 0) : null;
  const count = asNumber(qc?.count) ?? asNumber(firstPrimary.count) ?? rowCount;
  return {
    check: check === "Unavailable" ? "NA" : check,
    count,
  };
}

function checkMeaning(checkName: string): string {
  if (checkName === "Convergence") return "Sampling stable; estimates reliable.";
  if (checkName === "Baseline") return "Baseline component behaves as expected.";
  if (checkName === "BayesianPPP") return "Posterior predictive check passed.";
  if (checkName === "GoodnessOfFit") return "Model fit is acceptable.";
  if (checkName === "ROIConsistency") return "ROI outputs are stable and consistent.";
  return "Core model validity diagnostic.";
}

function strictStatusClass(status: DiagnosticStatus): string {
  return status.toLowerCase();
}

function pctFor(count: number, total: number): string {
  return total ? displayPercent((count / total) * 100) : "NA";
}

function shortRunId(value: unknown): string {
  const text = String(value || "").trim();
  if (!text) return "NA";
  const target = text.match(/target=([^|]+)/)?.[1];
  const mu = text.match(/mu=([^|]+)/)?.[1];
  const sigma = text.match(/sigma=([^|]+)/)?.[1];
  if (target && mu && sigma) return `${target} mu=${Number(mu).toFixed(1)} sigma=${Number(sigma).toFixed(1)}`;
  return text.length > 48 ? `${text.slice(0, 47)}...` : text;
}

function coreStatusSummary(row: DiagnosticCheckRow): string {
  const status = statusForCheck(row);
  const pass = asNumber(row.pass_count) || 0;
  const review = asNumber(row.review_count) || 0;
  const fail = asNumber(row.fail_count) || 0;
  if (status === "FAIL") return `${displayNumber(fail)} failed / ${displayNumber(pass)} passed`;
  if (status === "REVIEW") return `${displayNumber(review)} review / ${displayNumber(pass)} passed`;
  if (status === "PASS") return `${displayNumber(pass)} pass`;
  return "Unavailable";
}

function passRate(row: DiagnosticCheckRow, totalRuns: number): string {
  const pass = asNumber(row.pass_count) || 0;
  const denominator =
    pass + (asNumber(row.review_count) || 0) + (asNumber(row.fail_count) || 0) + (asNumber(row.unknown_count) || 0) || totalRuns;
  return denominator ? displayPercent((pass / denominator) * 100) : "NA";
}

export function RunAuditDiagnosticsPage() {
  const result = useCurrentResult();
  const { payload } = result;
  const diagnostics = selectDiagnostics(payload);
  const overview = diagnostics.overview || payload.diagnostics_overview || {};
  const checkRows = diagnostics.check_rows || [];
  const completedRuns = asNumber(overview.n_runs) || 0;
  const strictPass = asNumber(overview.pass_runs) || 0;
  const strictReview = asNumber(overview.review_runs) || 0;
  const strictFail = asNumber(overview.fail_runs) || 0;
  const strictUnknown = asNumber(overview.unknown_runs) || 0;
  const strictTotal = strictPass + strictReview + strictFail + strictUnknown || completedRuns;
  const core = diagnostics.core_model_health || deriveCoreHealth(checkRows, strictTotal);
  const priorAudit = diagnostics.prior_sensitivity_audit || derivePriorAudit(checkRows, strictTotal);
  const coreRows = orderedCoreRows(core.check_rows || checkRows);
  const ppsReviewRuns = asNumber(priorAudit.pps_any_channel_count) ?? asNumber(priorAudit.pps_review_runs) ?? 0;
  const corePassed = asNumber(core.passed_runs) || 0;
  const coreFailed = asNumber(core.failed_runs) || 0;
  const coreReview = asNumber(core.review_runs) || 0;
  const coreUnknown = asNumber(core.unknown_runs) || 0;
  const coreTotal = asNumber(core.total_runs) || strictTotal;
  const corePassRate = asNumber(core.pass_rate_pct) ?? (coreTotal ? (corePassed / coreTotal) * 100 : 0);
  const coreStatus: DiagnosticStatus = coreFailed > 0 ? "FAIL" : coreReview || coreUnknown ? "REVIEW" : corePassed ? "PASS" : "UNAVAILABLE";
  const primary = primaryReview(payload, checkRows);
  const targetBreakdownAvailable = Boolean(priorAudit.target_breakdown_available);
  const targetReview = asNumber(priorAudit.pps_target_channel_review_count) ?? asNumber(priorAudit.target_channel_review_runs);
  const nonTargetReview = asNumber(priorAudit.pps_non_target_only_review_count) ?? asNumber(priorAudit.non_target_only_review_runs);
  const ppsOverlap = asNumber(priorAudit.pps_review_convergence_fail_overlap_count) ?? asNumber(priorAudit.pps_convergence_fail_overlap_runs) ?? 0;
  const convergenceFailures = diagnostics.convergence_failure_rows || [];
  const ppsDonutPct = strictTotal ? Math.min(100, Math.max(0, (ppsReviewRuns / strictTotal) * 100)) : 0;
  const bottomLine =
    `Core diagnostics are healthy for ${displayNumber(corePassed)}/${displayNumber(coreTotal)} runs. ` +
    `High strict-review counts are mainly driven by PriorPosteriorShift; ${displayNumber(coreFailed)} runs need convergence rerun or exclusion.`;

  return (
    <SectionScaffold
      title="Run Audit & Diagnostics"
      summary="Model health, prior-sensitivity audit signals, and strict QC rollup for completed runs."
      sourceLabel={result.sourceLabel}
      sourceDetail={result.sourceDetail}
      sourceKind={result.sourceKind}
      activeRunId={result.activeRunId}
      runSummary={result.runSummary}
      buildResultsPath={result.buildResultsPath}
      headerAside={null}
    >
      <div className="run-audit-dashboard run-audit-dashboard--redesign">
        <section className="audit-summary-grid audit-summary-grid--four" aria-label="Run audit summary">
          <article className="audit-summary-card audit-summary-card--icon">
            <div className="audit-card-icon audit-card-icon--blue"><ListChecks size={24} /></div>
            <div>
              <span>Run Summary</span>
              <strong>{displayNumber(completedRuns || strictTotal)}</strong>
              <p>Completed Runs</p>
              <small>Generated {payload.meta?.generated_at || "NA"}</small>
            </div>
            <ContextualHelpButton sectionId="qc-status" label="Explain run diagnostics" />
          </article>

          <article className="audit-summary-card audit-summary-card--icon">
            <div className="audit-card-icon audit-card-icon--green"><ShieldCheck size={24} /></div>
            <div>
              <span>Core Model Health</span>
              <strong>{displayNumber(corePassed)} / {displayNumber(coreTotal)}</strong>
              <p>Runs Passed Core Diagnostics</p>
              {coreFailed > 0 ? <b className="audit-note audit-note--fail">{displayNumber(coreFailed)} convergence failures need rerun</b> : null}
              <small>Excludes prior sensitivity checks</small>
            </div>
            <ContextualHelpButton sectionId="qc-checks" label="Explain core diagnostics" />
          </article>

          <article className="audit-summary-card audit-summary-card--icon">
            <div className="audit-card-icon audit-card-icon--orange"><AlertTriangle size={24} /></div>
            <div>
              <span>Prior Sensitivity Signal</span>
              <strong>{displayNumber(ppsReviewRuns)} / {displayNumber(strictTotal)}</strong>
              <p>Runs Flagged by PriorPosteriorShift</p>
              <small>Audit signal, not automatic failure</small>
            </div>
            <ContextualHelpButton sectionId="primary-review-checks" label="Explain prior sensitivity reviews" />
          </article>

          <article className="audit-summary-card audit-action-card">
            <div className="audit-card-icon audit-card-icon--purple"><Crosshair size={24} /></div>
            <div>
              <span>Action Needed</span>
              <ul className="audit-action-queue">
                <li><b className="fail">{displayNumber(coreFailed)}</b> <span>Rerun required: convergence failures</span></li>
                {targetBreakdownAvailable ? (
                  <>
                    <li><b className="review">{displayNumber(targetReview)}</b> <span>Target-channel reviews</span></li>
                    <li><b>{displayNumber(nonTargetReview)}</b> <span>Non-target-only reviews</span></li>
                  </>
                ) : (
                  <>
                    <li><b className="review">{displayNumber(ppsReviewRuns)}</b> <span>Audit review: PPS flags</span></li>
                    <li><b className="neutral">!</b> <span>Data gap: target/non-target breakdown unavailable</span></li>
                  </>
                )}
              </ul>
            </div>
          </article>
        </section>

        <section className="audit-bottom-line">
          <Info size={18} />
          <p>{bottomLine}</p>
        </section>

        <section className="audit-triad-grid" aria-label="Diagnostic interpretation panels">
          <article className="audit-card audit-core-panel">
            <div className="section-title-row section-title-row--compact">
              <h3>Core Diagnostics Overview</h3>
              <ContextualHelpButton sectionId="qc-checks" label="Explain core diagnostics" />
            </div>
            <div className="audit-core-layout">
              <div className="audit-score-donut audit-score-donut--core" style={{ "--score-pct": `${Math.max(0, Math.min(100, corePassRate))}%` } as CSSProperties}>
                <div>
                  <strong>{displayNumber(corePassRate, 1)}%</strong>
                  <span>Core Checks Passed</span>
                </div>
              </div>
              <div className="audit-core-checks">
                <div className="audit-mini-legend">
                  <span><i className="status-dot status-dot--pass" />Passed {displayNumber(corePassed)}</span>
                  <span><i className="status-dot status-dot--review" />Review {displayNumber(coreReview)}</span>
                  <span><i className="status-dot status-dot--fail" />Failed {displayNumber(coreFailed)}</span>
                </div>
                <div className="audit-check-list">
                  {coreRows.map((row) => {
                    const name = displayCheckName(row.check);
                    const status = statusForCheck(row);
                    return (
                      <div className="audit-check-list-row" key={name}>
                        <b>{name}</b>
                        <span className={`audit-pill audit-pill--${strictStatusClass(status)}`}>{status}</span>
                        <small>
                          {status === "FAIL"
                            ? `${displayNumber(row.pass_count)} pass · ${displayNumber(row.fail_count)} fail`
                            : status === "REVIEW"
                              ? `${displayNumber(row.pass_count)} pass · ${displayNumber(row.review_count)} review`
                              : coreStatusSummary(row)}
                        </small>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
            <div className="audit-interpretation audit-interpretation--info">
              <Info size={17} />
              <p>Model is largely healthy. {displayNumber(coreFailed)} runs failed convergence diagnostics. Review or rerun these runs before drawing strong conclusions.</p>
            </div>
          </article>

          <article className="audit-card audit-prior-panel">
            <div className="section-title-row section-title-row--compact">
              <h3>Prior Sensitivity Audit</h3>
              <ContextualHelpButton sectionId="primary-review-checks" label="Explain PriorPosteriorShift" />
            </div>
            <div className="audit-prior-layout">
              <div className="audit-prior-donut" style={{ "--score-pct": `${ppsDonutPct}%` } as CSSProperties}>
                <div>
                  <strong>{displayNumber(ppsReviewRuns)}</strong>
                  <span>PPS Review Flags</span>
                </div>
              </div>
              <div className="audit-breakdown-list">
                <div>
                  <b>Target-channel PPS review</b>
                  <strong>{targetBreakdownAvailable ? displayNumber(targetReview) : "NA"}</strong>
                  <small>{targetBreakdownAvailable ? "Directly relevant to tested prior" : "Breakdown unavailable"}</small>
                </div>
                <div>
                  <b>Non-target-only PPS review</b>
                  <strong>{targetBreakdownAvailable ? displayNumber(nonTargetReview) : "NA"}</strong>
                  <small>{targetBreakdownAvailable ? "Likely audit/context signal" : "See note below"}</small>
                </div>
                <div>
                  <b>Overlap with convergence fail</b>
                  <strong>{displayNumber(ppsOverlap)}</strong>
                  <small>Counted as FAIL at run level</small>
                </div>
              </div>
            </div>
            <div className="audit-interpretation audit-interpretation--review">
              <Info size={17} />
              <p>
                PriorPosteriorShift is expected to fire often in prior-sensitivity experiments because checks are applied across channels.
                {targetBreakdownAvailable
                  ? " Interpret as sensitivity / weak posterior update signal, not broad model failure."
                  : " Target/non-target split is available only in regenerated reports with PPS breakdown fields."}
              </p>
            </div>
          </article>

          <div className="audit-right-stack">
            <article className="audit-card audit-strict-panel">
              <div className="section-title-row section-title-row--compact">
                <h3>Strict QC Rollup (includes PPS reviews)</h3>
                <ContextualHelpButton sectionId="qc-status" label="Explain strict QC rollup" />
              </div>
              <div className="audit-strict-mix">
                <div className="pass"><span>PASS</span><strong>{displayNumber(strictPass)}</strong><small>{pctFor(strictPass, strictTotal)}</small></div>
                <div className="review"><span>REVIEW</span><strong>{displayNumber(strictReview)}</strong><small>{pctFor(strictReview, strictTotal)}</small></div>
                <div className="fail"><span>FAIL</span><strong>{displayNumber(strictFail)}</strong><small>{pctFor(strictFail, strictTotal)}</small></div>
              </div>
              <p>Meridian-style rollup; stricter than Core Model Health.</p>
            </article>
            <article className="audit-card audit-primary-panel">
              <div className="section-title-row section-title-row--compact">
                <h3>Why are reviews high?</h3>
                <ContextualHelpButton sectionId="primary-review-checks" label="Explain primary review signal" />
              </div>
              <div className="audit-review-driver">
                <span>Main driver</span>
                <strong>{primary.check}</strong>
                <p>{primary.count === null ? "Strict review count unavailable." : `${displayNumber(primary.count)} strict-review runs include this signal.`}</p>
                <p>Included in strict rollup; not treated as core model failure.</p>
              </div>
            </article>
          </div>
        </section>

        <section className="audit-bottom-grid audit-bottom-grid--redesign">
          <article className="audit-card">
            <div className="section-title-row section-title-row--compact">
              <h3>Core Model Diagnostics Across Runs</h3>
              <ContextualHelpButton sectionId="qc-checks" label="Explain core diagnostics table" />
            </div>
            <div className="audit-table-wrap">
              <table className="audit-check-table audit-check-table--core">
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Pass</th>
                    <th>Review</th>
                    <th>Fail</th>
                    <th>Missing</th>
                    <th>Pass Rate</th>
                    <th>What it means</th>
                  </tr>
                </thead>
                <tbody>
                  {coreRows.map((row) => {
                    const name = displayCheckName(row.check);
                    return (
                      <tr key={name}>
                        <td>{name}</td>
                        <td className="table-pass">{displayNumber(row.pass_count)}</td>
                        <td className="table-review">{displayNumber(row.review_count)}</td>
                        <td className="table-fail">{displayNumber(row.fail_count)}</td>
                        <td>{displayNumber(row.unknown_count)}</td>
                        <td>{passRate(row, coreTotal)}</td>
                        <td>{checkMeaning(name)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="audit-interpretation audit-interpretation--pass">
              <CheckCircle2 size={17} />
              <p>Core diagnostics look good overall. Focus on the {displayNumber(coreFailed)} convergence failures.</p>
            </div>
          </article>

          <article className="audit-card">
            <div className="section-title-row section-title-row--compact">
              <h3>Prior Sensitivity / Audit Across Runs</h3>
              <ContextualHelpButton sectionId="primary-review-checks" label="Explain prior sensitivity table" />
            </div>
            <div className="audit-table-wrap">
              <table className="audit-check-table audit-check-table--audit">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Count</th>
                    <th>Interpretation</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>PriorPosteriorShift any channel</td>
                    <td>{displayNumber(ppsReviewRuns)}</td>
                    <td>Posterior did not significantly move from prior for at least one channel.</td>
                  </tr>
                  <tr>
                    <td>Target-channel PPS review</td>
                    <td>{targetBreakdownAvailable ? displayNumber(targetReview) : "NA"}</td>
                    <td>{targetBreakdownAvailable ? "Review before strong channel-level claims." : "Available only in regenerated reports with PPS breakdown."}</td>
                  </tr>
                  <tr>
                    <td>Non-target-only PPS review</td>
                    <td>{targetBreakdownAvailable ? displayNumber(nonTargetReview) : "NA"}</td>
                    <td>{targetBreakdownAvailable ? "Contextual audit signal; not model failure." : "Available only in regenerated reports with PPS breakdown."}</td>
                  </tr>
                  <tr>
                    <td>PPS review + convergence fail overlap</td>
                    <td>{displayNumber(ppsOverlap)}</td>
                    <td>Counted as FAIL at run level; rerun/exclude before interpretation.</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="audit-interpretation audit-interpretation--review">
              <Info size={17} />
              <p>These are sensitivity / audit signals, not automatic model failures. Interpret directionally and in context of experiment design.</p>
            </div>
          </article>

          <article className="audit-card">
            <div className="section-title-row section-title-row--compact">
              <h3>{displayNumber(coreFailed)} Convergence Failures</h3>
              <ContextualHelpButton sectionId="warnings" label="Explain convergence failures" />
            </div>
            <div className="audit-table-wrap">
              <table className="audit-check-table audit-check-table--failures">
                <thead>
                  <tr>
                    <th>Target / Channel</th>
                    <th>mu</th>
                    <th>sigma</th>
                    <th>R-hat Trigger</th>
                    <th>Param</th>
                    <th>Max R</th>
                  </tr>
                </thead>
                <tbody>
                  {convergenceFailures.length ? (
                    convergenceFailures.map((row: ConvergenceFailureRow, index: number) => (
                      <tr key={`${row.run_id || "failure"}-${index}`}>
                        <td>{row.target_channel || shortRunId(row.run_id)}</td>
                        <td>{displayNumber(row.roi_prior_mu, 1)}</td>
                        <td>{displayNumber(row.roi_prior_sigma, 1)}</td>
                        <td>{row.r_hat_trigger || "Convergence"}</td>
                        <td>{row.parameter || "NA"}</td>
                        <td className="table-fail">{displayNumber(row.max_r_hat, 2)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6}>
                        {coreFailed > 0
                          ? "Convergence failure details are unavailable in this payload; use the run-level diagnostics source for run_id and fail reason."
                          : "No convergence failures in the selected payload."}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {coreFailed > 0 ? (
              <div className="audit-interpretation audit-interpretation--fail">
                <AlertTriangle size={17} />
                <p>Meridian convergence threshold is 1.20. R-hat at or above this threshold is reported as FAIL. Rerun or exclude these runs.</p>
              </div>
            ) : null}
          </article>
        </section>

        <p className="audit-footnote">Note: Core Model Health excludes PriorPosteriorShift by design in this prior-sensitivity analysis. For overall QC including sensitivity checks, see Strict QC Rollup.</p>
      </div>
    </SectionScaffold>
  );
}
