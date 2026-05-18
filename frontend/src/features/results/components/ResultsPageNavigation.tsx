import { Link } from "react-router-dom";

type ResultsPageNavigationProps = {
  previousPath?: string;
  previousLabel?: string;
  nextPath: string;
  nextLabel: string;
  nextActionLabel?: string;
};

export function ResultsPageNavigation({
  previousPath,
  previousLabel,
  nextPath,
  nextLabel,
  nextActionLabel = "Continue",
}: ResultsPageNavigationProps) {
  const isFinalAction = nextActionLabel.toLowerCase().includes("overview");
  const helperLabel = nextLabel.replace(/^Results\s*\/\s*/i, "");

  return (
    <nav className="results-bottom-nav" aria-label="Results page navigation">
      <div className="results-bottom-nav__side results-bottom-nav__side--back">
        {previousPath ? (
          <>
            <Link className="results-nav-button results-nav-button--back" to={previousPath} aria-label={`Back to ${previousLabel || "previous screen"}`}>
              <span className="results-nav-button__icon results-nav-button__icon--back" aria-hidden="true" />
              Back
            </Link>
            {previousLabel ? <span className="results-nav-context">{previousLabel}</span> : null}
          </>
        ) : null}
      </div>

      <div className="results-bottom-nav__side results-bottom-nav__side--next">
        <Link className="results-nav-button results-nav-button--continue" to={nextPath} aria-label={`${nextActionLabel} to ${nextLabel}`}>
          {nextActionLabel}
          <span className="results-nav-button__icon results-nav-button__icon--continue" aria-hidden="true" />
        </Link>
        <div className="results-next-screen">
          <span>{isFinalAction ? "Final screen" : "Next screen:"}</span>
          <strong>{helperLabel}</strong>
        </div>
      </div>
    </nav>
  );
}
