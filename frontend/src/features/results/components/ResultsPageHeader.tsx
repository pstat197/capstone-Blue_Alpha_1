import type { ReactNode } from "react";

type ResultsPageHeaderProps = {
  title: string;
  summary?: string;
  aside?: ReactNode;
};

export function ResultsPageHeader({ title, summary, aside }: ResultsPageHeaderProps) {
  return (
    <header className="results-page-header">
      <div>
        <h2>{title}</h2>
        {summary ? <p>{summary}</p> : null}
      </div>
      {aside ? <div className="results-page-header__aside">{aside}</div> : null}
    </header>
  );
}
