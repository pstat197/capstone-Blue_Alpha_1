import type { ReactNode } from "react";
import { ReadOnlyNotice } from "./ReadOnlyNotice";

type SectionScaffoldProps = {
  title: string;
  summary: string;
  sourceLabel?: string;
  sourceDetail?: string;
  sourceKind?: "api" | "bundled" | "mock" | "error";
  children: ReactNode;
};

export function SectionScaffold({ title, summary, sourceKind = "mock", children }: SectionScaffoldProps) {
  return (
    <article className="result-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Post-run Results</span>
          <h2>{title}</h2>
        </div>
        <span className="mode-chip mode-chip--post-run">post-run</span>
      </div>
      <p className="page-summary">{summary}</p>
      {sourceKind === "error" ? (
        <div className="content-panel">
          <h3>Result Payload Unavailable</h3>
          <p className="muted">
            This run does not have a loadable results payload yet.
          </p>
        </div>
      ) : null}
      <ReadOnlyNotice />
      {children}
    </article>
  );
}
