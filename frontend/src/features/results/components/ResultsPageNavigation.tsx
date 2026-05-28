import { Link } from "react-router-dom";

type ResultsPageNavigationProps = {
  previousPath?: string;
  previousLabel?: string;
  nextPath: string;
  nextLabel: string;
  nextActionLabel?: string;
  secondaryActionPath?: string;
  secondaryActionLabel?: string;
};

export function ResultsPageNavigation({
  previousPath,
  previousLabel,
  nextPath,
  nextLabel,
  nextActionLabel = "Continue",
  secondaryActionPath,
  secondaryActionLabel,
}: ResultsPageNavigationProps) {
  const hasSecondaryAction = Boolean(secondaryActionPath && secondaryActionLabel);
  const helperLabel = nextLabel.replace(/^Results\s*\/\s*/i, "");
  const previousContextLabel = previousLabel === "Model Structure" ? "Run Structure" : previousLabel;

  return (
    <nav className="results-bottom-nav" aria-label="Results page navigation">
      <div className="results-bottom-nav__side results-bottom-nav__side--back">
        {previousPath ? (
          <>
            <Link className="results-nav-button results-nav-button--back" to={previousPath} aria-label={`Back to ${previousLabel || "previous screen"}`}>
              <span className="results-nav-button__icon results-nav-button__icon--back" aria-hidden="true" />
              Back
            </Link>
            {previousContextLabel ? <span className="results-nav-context">Previous: {previousContextLabel}</span> : null}
          </>
        ) : null}
      </div>

      <div className="results-bottom-nav__side results-bottom-nav__side--next">
        <div className="results-nav-action-row">
          {hasSecondaryAction ? (
            <Link className="results-nav-button results-nav-button--secondary" to={secondaryActionPath!}>
              {secondaryActionLabel}
            </Link>
          ) : null}
          <Link className="results-nav-button results-nav-button--continue" to={nextPath} aria-label={`${nextActionLabel} to ${nextLabel}`}>
            {nextActionLabel}
            <span className="results-nav-button__icon results-nav-button__icon--continue" aria-hidden="true" />
          </Link>
        </div>
        <div className="results-next-screen">
          <span>{hasSecondaryAction ? "Next:" : "Next screen:"}</span>
          <strong>{helperLabel}</strong>
        </div>
      </div>
    </nav>
  );
}
