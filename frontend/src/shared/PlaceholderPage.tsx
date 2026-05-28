import type { ReactNode } from "react";

type PlaceholderPageProps = {
  title: string;
  sectionLabel: string;
  mode: "pre-run" | "execution" | "post-run";
  summary: string;
  primaryItems: string[];
  boundaryNote: ReactNode;
};

export function PlaceholderPage({
  title,
  sectionLabel,
  mode,
  summary,
  primaryItems,
  boundaryNote,
}: PlaceholderPageProps) {
  return (
    <article className="placeholder-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{sectionLabel}</span>
          <h2>{title}</h2>
        </div>
        <span className={`mode-chip mode-chip--${mode}`}>{mode}</span>
      </div>

      <p className="page-summary">{summary}</p>

      <section className="content-panel" aria-label={`${title} planned responsibilities`}>
        <h3>Phase 1 Responsibilities</h3>
        <div className="responsibility-grid">
          {primaryItems.map((item) => (
            <div className="responsibility-card" key={item}>
              {item}
            </div>
          ))}
        </div>
      </section>

      <section className="boundary-panel" aria-label={`${title} boundary`}>
        <h3>Product Boundary</h3>
        <p>{boundaryNote}</p>
      </section>
    </article>
  );
}
