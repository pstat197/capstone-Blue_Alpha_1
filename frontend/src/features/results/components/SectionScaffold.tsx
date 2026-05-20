import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import type { RunStatus } from "../../../api/types";
import { monitorNavItem, resultNavItems } from "../../../app/navigation";
import { ResultsPageHeader } from "./ResultsPageHeader";
import { ResultsPageNavigation } from "./ResultsPageNavigation";

type SectionScaffoldProps = {
  title: string;
  summary: string;
  sourceLabel?: string;
  sourceDetail?: string;
  sourceKind?: "api" | "loading" | "missing" | "error";
  headerAside?: ReactNode;
  titleStatusChip?: string;
  activeRunId?: string | null;
  runSummary?: RunStatus | null;
  buildResultsPath?: (pathOrSlug: string) => string;
  children: ReactNode;
};

export function SectionScaffold({
  title,
  summary,
  sourceLabel,
  sourceDetail,
  sourceKind = "missing",
  headerAside,
  runSummary,
  buildResultsPath,
  children,
}: SectionScaffoldProps) {
  const location = useLocation();
  const pathParts = location.pathname.split("/").filter(Boolean);
  const currentSlug = pathParts[pathParts.length - 1];
  const currentIndex = resultNavItems.findIndex((item) => location.pathname === item.path || item.path.endsWith(`/${currentSlug}`));
  const previousItem = currentIndex > 0 ? resultNavItems[currentIndex - 1] : currentIndex === 0 ? monitorNavItem : null;
  const nextItem = currentIndex > -1 && currentIndex < resultNavItems.length - 1 ? resultNavItems[currentIndex + 1] : null;
  const finalItem = resultNavItems[0];
  const pathFor = buildResultsPath || ((path: string) => path);
  const monitorPath = runSummary?.run_id ? `/workflow/run-monitor?run_id=${encodeURIComponent(runSummary.run_id)}` : "/workflow/run-monitor";
  const statusMessage =
    sourceKind === "loading"
      ? {
          title: "Loading Results",
          body: "Loading generated dashboard artifacts for this run.",
        }
        : sourceKind === "missing"
          ? {
            title: "Results Not Selected",
            body: "Results are not selected because no completed run could be resolved.",
          }
        : sourceKind === "error"
          ? {
              title: "Results Are Not Available",
              body: "Results are not available for this run yet. Please check whether dashboard artifacts were generated.",
            }
          : null;

  return (
    <article className="result-page">
      <ResultsPageHeader
        title={title}
        summary={summary}
        aside={headerAside || (sourceKind === "api" && sourceLabel ? (
          <div className="result-source-chip">
            <span>{sourceLabel}</span>
            {sourceDetail ? <small>{sourceDetail}</small> : null}
          </div>
        ) : null)}
      />
      {statusMessage ? (
        <div className="content-panel">
          <h3>{statusMessage.title}</h3>
          <p className="muted">{statusMessage.body}</p>
        </div>
      ) : null}
      {statusMessage ? null : children}
      {!statusMessage ? (
        <ResultsPageNavigation
          previousPath={previousItem?.section === "monitor" ? monitorPath : previousItem ? pathFor(previousItem.path) : undefined}
          previousLabel={previousItem?.label}
          nextPath={nextItem ? pathFor(nextItem.path) : pathFor(finalItem.path)}
          nextLabel={nextItem?.label || finalItem.label}
          nextActionLabel={nextItem ? "Continue" : "Back to Overview"}
        />
      ) : null}
    </article>
  );
}
