import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getResultHistory } from "../../../api/results";
import { getLatestCompletedRun } from "../../../api/runs";
import type { ResultHistoryItem, RunStatus } from "../../../api/types";
import { ChannelLogo, displayChannelName } from "../../workflow/data/channelRegistry";
import { ResultsPageHeader } from "../components/ResultsPageHeader";
import { formatNumber } from "../data/resultSelectors";

const rowsPerPageOptions = [6, 10, 20];

type SortOrder = "newest" | "oldest";

function formatGeneratedAt(raw?: string | null) {
  if (!raw) return "Date unavailable";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function generatedTime(item: ResultHistoryItem) {
  const parsed = new Date(item.generated_at || "").getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

function qcSummary(item: ResultHistoryItem) {
  return {
    pass: item.qc_pass_runs ?? 0,
    review: item.qc_review_runs ?? 0,
    fail: item.qc_fail_runs ?? 0,
  };
}

function qcLabel(item: ResultHistoryItem) {
  const qc = qcSummary(item);
  return `PASS ${formatNumber(qc.pass)} / REVIEW ${formatNumber(qc.review)} / FAIL ${formatNumber(qc.fail)}`;
}

function qcTone(item: ResultHistoryItem) {
  const qc = qcSummary(item);
  if (qc.fail > 0) return "fail";
  if (qc.review > 0) return "review";
  return "pass";
}

function compactPath(item: ResultHistoryItem) {
  const path = item.payload_path || "Path unavailable";
  const parts = path.split("/");
  if (parts.length <= 3) return path;
  return `.../${parts.slice(-2).join("/")}`;
}

function runName(item: ResultHistoryItem) {
  return item.display_result_id || item.output_tag || item.run_id;
}

function kpiPath(item: ResultHistoryItem) {
  return item.kpi_path || item.kpi || "Unavailable";
}

function subtitle(item: ResultHistoryItem) {
  return `${item.kpi || "KPI unavailable"} · ${kpiPath(item)} · ${formatNumber(item.channel_count)} channel${item.channel_count === 1 ? "" : "s"} · ${formatNumber(item.completed_runs ?? 0)} runs`;
}

function uniqueValues(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((value) => value?.trim()).filter(Boolean) as string[])).sort((a, b) => a.localeCompare(b));
}

function pageNumbers(currentPage: number, totalPages: number) {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1);
  const pages = new Set([1, totalPages, currentPage, currentPage - 1, currentPage + 1]);
  return Array.from(pages).filter((page) => page >= 1 && page <= totalPages).sort((a, b) => a - b);
}

function channelsMatch(item: ResultHistoryItem, channelFilter: string) {
  if (channelFilter === "all") return true;
  return item.channels.some((channel) => channel.toLowerCase() === channelFilter.toLowerCase());
}

function qcMatches(item: ResultHistoryItem, statusFilter: string) {
  if (statusFilter === "all") return true;
  const qc = qcSummary(item);
  if (statusFilter === "pass") return qc.pass > 0;
  if (statusFilter === "review") return qc.review > 0;
  if (statusFilter === "fail") return qc.fail > 0;
  return true;
}

function ChannelStack({ channels }: { channels: string[] }) {
  const visible = channels.slice(0, 4);
  return (
    <span className="history-channel-stack">
      {visible.map((channel) => (
        <span title={displayChannelName(channel)} key={channel}>
          <ChannelLogo channel={channel} />
        </span>
      ))}
      {channels.length > visible.length ? <span className="history-channel-more">+{channels.length - visible.length}</span> : null}
    </span>
  );
}

export function ResultsHistoryPage() {
  const [items, setItems] = useState<ResultHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [latestRun, setLatestRun] = useState<RunStatus | null>(null);
  const [latestRunError, setLatestRunError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [kpiFilter, setKpiFilter] = useState("all");
  const [channelFilter, setChannelFilter] = useState("all");
  const [qcFilter, setQcFilter] = useState("all");
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest");
  const [page, setPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  const loadHistory = () => {
    setLoading(true);
    getResultHistory()
      .then((response) => {
        setItems(response.items);
        setSelectedId((current) => current || response.items[0]?.history_id || null);
        setError(null);
      })
      .catch((historyError: unknown) => {
        setItems([]);
        setSelectedId(null);
        setError(historyError instanceof Error ? historyError.message : "Saved results could not be loaded.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(loadHistory, []);

  useEffect(() => {
    getLatestCompletedRun()
      .then((run) => {
        setLatestRun(run);
        setLatestRunError(null);
      })
      .catch((latestError: unknown) => {
        setLatestRun(null);
        setLatestRunError(latestError instanceof Error ? latestError.message : "No latest completed run is available.");
      });
  }, []);

  const totalReports = items.length;
  const kpiOptions = useMemo(() => uniqueValues(items.map((item) => kpiPath(item))), [items]);
  const channelOptions = useMemo(() => uniqueValues(items.flatMap((item) => item.channels)), [items]);
  const mostRecent = useMemo(() => [...items].sort((a, b) => generatedTime(b) - generatedTime(a))[0] || null, [items]);
  const distinctKpis = kpiOptions.length;

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    return [...items]
      .filter((item) => {
        const name = runName(item).toLowerCase();
        const id = item.run_id.toLowerCase();
        const configId = (item.config_fingerprint || "").toLowerCase();
        return !query || name.includes(query) || id.includes(query) || configId.includes(query);
      })
      .filter((item) => kpiFilter === "all" || kpiPath(item) === kpiFilter)
      .filter((item) => channelsMatch(item, channelFilter))
      .filter((item) => qcMatches(item, qcFilter))
      .sort((a, b) => (sortOrder === "newest" ? generatedTime(b) - generatedTime(a) : generatedTime(a) - generatedTime(b)));
  }, [channelFilter, items, kpiFilter, qcFilter, search, sortOrder]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / rowsPerPage));
  const currentPage = Math.min(page, totalPages);
  const startIndex = filteredItems.length ? (currentPage - 1) * rowsPerPage : 0;
  const endIndex = Math.min(startIndex + rowsPerPage, filteredItems.length);
  const pagedItems = filteredItems.slice(startIndex, endIndex);
  const selectedItem = items.find((item) => item.history_id === selectedId) || pagedItems[0] || items[0] || null;
  const latestRunPath = latestRun ? `/results/overview?run_id=${encodeURIComponent(latestRun.run_id)}` : "";

  useEffect(() => {
    setPage(1);
  }, [channelFilter, kpiFilter, qcFilter, rowsPerPage, search, sortOrder]);

  useEffect(() => {
    if (!selectedId && items.length) {
      setSelectedId(items[0].history_id);
    }
  }, [items, selectedId]);

  return (
    <article className="result-page results-history-page">
      <ResultsPageHeader
        title="Saved Results"
        summary="Open a previous local report, compare it with the latest completed run, or return to Run Monitor."
      />

      <div className="history-segmented-control" role="tablist" aria-label="Results mode">
        {latestRun ? (
          <Link role="tab" aria-selected="false" to={latestRunPath} className="history-segment" title="Open the latest completed run.">
            Latest Run
          </Link>
        ) : (
          <button role="tab" aria-selected="false" className="history-segment history-segment--disabled" type="button" disabled title={latestRunError || "No latest completed run is available."}>
            Latest Run
          </button>
        )}
        <Link role="tab" aria-selected="true" aria-current="page" to="/results/history" className="history-segment history-segment--active">
          Saved History
        </Link>
      </div>

      <section className="history-summary-grid" aria-label="Saved result summary">
        <article className="history-summary-card">
          <span className="history-summary-icon history-summary-icon--reports" aria-hidden="true" />
          <div>
            <span>Total Saved Reports</span>
            <strong>{formatNumber(totalReports)}</strong>
            <small>Across {formatNumber(distinctKpis)} KPI path{distinctKpis === 1 ? "" : "s"}</small>
          </div>
        </article>
        <article className="history-summary-card">
          <span className="history-summary-icon history-summary-icon--recent" aria-hidden="true" />
          <div>
            <span>Most Recent Report</span>
            <strong>{mostRecent ? formatGeneratedAt(mostRecent.generated_at) : "Unavailable"}</strong>
            <small>{mostRecent ? runName(mostRecent) : "No local reports found"}</small>
          </div>
        </article>
        <article className="history-summary-card">
          <span className="history-summary-icon history-summary-icon--kpi" aria-hidden="true" />
          <div>
            <span>Distinct KPIs</span>
            <strong>{formatNumber(distinctKpis)}</strong>
            <small>{kpiOptions.slice(0, 2).join(", ") || "No KPI metadata"}</small>
          </div>
        </article>
      </section>

      {error ? (
        <div className="results-history-empty" role="status">
          <h3>Saved results unavailable</h3>
          <p>{error}</p>
        </div>
      ) : null}

      {!error && !loading && !items.length ? (
        <div className="results-history-empty" role="status">
          <h3>No saved results found yet.</h3>
          <p>No saved results found yet. Complete a run first, or generate a dashboard report under data/output/03_reports.</p>
        </div>
      ) : null}

      {!error && items.length ? (
        <section className="history-content-grid">
          <div className="history-results-column">
            <section className="history-filter-bar" aria-label="Saved result filters">
              <label className="history-search">
                <span>Search</span>
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search run name or ID..." />
              </label>
              <label>
                <span>KPI Path</span>
                <select value={kpiFilter} onChange={(event) => setKpiFilter(event.target.value)}>
                  <option value="all">All</option>
                  {kpiOptions.map((kpi) => <option value={kpi} key={kpi}>{kpi}</option>)}
                </select>
              </label>
              <label>
                <span>Channels</span>
                <select value={channelFilter} onChange={(event) => setChannelFilter(event.target.value)}>
                  <option value="all">All</option>
                  {channelOptions.map((channel) => <option value={channel} key={channel}>{displayChannelName(channel)}</option>)}
                </select>
              </label>
              <label>
                <span>QC Status</span>
                <select value={qcFilter} onChange={(event) => setQcFilter(event.target.value)}>
                  <option value="all">All</option>
                  <option value="pass">Pass</option>
                  <option value="review">Review</option>
                  <option value="fail">Fail</option>
                </select>
              </label>
              <label>
                <span>Sort by</span>
                <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value as SortOrder)}>
                  <option value="newest">Generated (Newest)</option>
                  <option value="oldest">Generated (Oldest)</option>
                </select>
              </label>
            </section>

            <div className="history-results-list">
              {loading ? <p className="muted">Scanning local report artifacts.</p> : null}
              {!loading && !pagedItems.length ? (
                <div className="results-history-empty" role="status">
                  <h3>No saved results match these filters.</h3>
                  <p>Adjust the search, KPI, channel, or QC filters to browse older local reports.</p>
                </div>
              ) : null}
              {pagedItems.map((item) => {
                const isSelected = item.history_id === selectedItem?.history_id;
                return (
                  <article
                    className={`history-result-row ${isSelected ? "history-result-row--selected" : ""}`}
                    key={item.history_id}
                    onClick={() => setSelectedId(item.history_id)}
                    onKeyDown={(event) => {
                      if ((event.key === "Enter" || event.key === " ") && event.target === event.currentTarget) {
                        event.preventDefault();
                        setSelectedId(item.history_id);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                  >
                    <div className="history-run-cell" title={runName(item)}>
                      <strong>{runName(item)}</strong>
                      <small>{subtitle(item)}</small>
                    </div>
                    <div className="history-metric-cell">
                      <span className="history-cell-label">Generated</span>
                      <strong>{formatGeneratedAt(item.generated_at)}</strong>
                    </div>
                    <div className="history-metric-cell">
                      <span className="history-cell-label">KPI Path</span>
                      <strong>{kpiPath(item)}</strong>
                    </div>
                    <div className="history-metric-cell history-channel-cell">
                      <span className="history-cell-label">Channels</span>
                      <strong>{formatNumber(item.channel_count)} channel{item.channel_count === 1 ? "" : "s"}</strong>
                      {item.channels.length ? <ChannelStack channels={item.channels} /> : <small>Unavailable</small>}
                    </div>
                    <div className="history-metric-cell">
                      <span className="history-cell-label">Completed Runs</span>
                      <strong>{formatNumber(item.completed_runs ?? 0)}</strong>
                    </div>
                    <div className="history-metric-cell">
                      <span className="history-cell-label">QC Mix</span>
                      <strong className={`history-qc history-qc--${qcTone(item)}`}>{qcLabel(item)}</strong>
                    </div>
                    <div className="history-metric-cell history-path-cell" title={item.payload_path}>
                      <span className="history-cell-label">Payload Path</span>
                      <strong>{compactPath(item)}</strong>
                    </div>
                    <div className="history-row-actions">
                      <button
                        className="history-mini-button"
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedId(item.history_id);
                        }}
                      >
                        Preview
                      </button>
                      <Link
                        className="history-mini-button history-mini-button--primary"
                        to={`/results/overview?history_id=${encodeURIComponent(item.history_id)}`}
                        onClick={(event) => event.stopPropagation()}
                      >
                        Open Result
                      </Link>
                      <button
                        className="history-overflow-button"
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedId(item.history_id);
                        }}
                        aria-label={`More actions for ${runName(item)}`}
                      >
                        ...
                      </button>
                    </div>
                  </article>
                );
              })}
              <footer className="history-pagination">
                <span>
                  Showing {filteredItems.length ? formatNumber(startIndex + 1) : 0} to {formatNumber(endIndex)} of {formatNumber(filteredItems.length)} results
                </span>
                <div className="history-page-controls">
                  <button type="button" disabled={currentPage <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</button>
                  {pageNumbers(currentPage, totalPages).map((pageNumber, index, pages) => (
                    <span key={pageNumber} className="history-page-number-wrap">
                      {index > 0 && pageNumber - pages[index - 1] > 1 ? <i>...</i> : null}
                      <button className={pageNumber === currentPage ? "history-page-number--active" : ""} type="button" onClick={() => setPage(pageNumber)}>
                        {pageNumber}
                      </button>
                    </span>
                  ))}
                  <button type="button" disabled={currentPage >= totalPages} onClick={() => setPage((current) => Math.min(totalPages, current + 1))}>Next</button>
                </div>
                <label className="history-rows-control">
                  <span>Rows per page</span>
                  <select value={rowsPerPage} onChange={(event) => setRowsPerPage(Number(event.target.value))}>
                    {rowsPerPageOptions.map((option) => <option value={option} key={option}>{option}</option>)}
                  </select>
                </label>
              </footer>
            </div>
          </div>

          <aside className="history-selected-panel">
            {selectedItem ? (
              <>
                <div className="history-selected-heading">
                  <span>Selected Report</span>
                  <button type="button" onClick={() => setSelectedId(null)} aria-label="Clear selected report">x</button>
                </div>
                <h3>{runName(selectedItem)}</h3>
                <p>Result ID: {runName(selectedItem)}</p>
                <dl className="history-detail-list">
                  <div><dt>Original CSV</dt><dd>{selectedItem.original_csv_filename || "Unavailable"}</dd></div>
                  <div><dt>Config ID</dt><dd>{selectedItem.config_fingerprint || "Unavailable"}</dd></div>
                  <div><dt>Generated</dt><dd>{formatGeneratedAt(selectedItem.generated_at)}</dd></div>
                  <div><dt>KPI Path</dt><dd>{kpiPath(selectedItem)}</dd></div>
                  <div><dt>Channels</dt><dd>{formatNumber(selectedItem.channel_count)} {selectedItem.channels.length ? <ChannelStack channels={selectedItem.channels} /> : null}</dd></div>
                  <div><dt>Completed Runs</dt><dd>{formatNumber(selectedItem.completed_runs ?? 0)}</dd></div>
                  <div><dt>QC Mix</dt><dd>{qcLabel(selectedItem)}</dd></div>
                  <div><dt>Payload Path</dt><dd title={selectedItem.payload_path}>{compactPath(selectedItem)}</dd></div>
                </dl>
                <div className="history-selected-actions">
                  <Link className="history-button history-button--primary" to={`/results/overview?history_id=${encodeURIComponent(selectedItem.history_id)}`}>
                    Open in Dashboard
                  </Link>
                  {latestRun ? (
                    <Link className="history-button history-button--secondary" to={latestRunPath}>
                      Compare to Latest
                    </Link>
                  ) : (
                    <button className="history-button history-button--secondary" type="button" disabled title={latestRunError || "No latest completed run is available."}>
                      Compare to Latest
                    </button>
                  )}
                </div>
              </>
            ) : (
              <div className="history-panel-empty">
                <h3>Selected Report</h3>
                <p>Choose Preview on a saved result to inspect local report metadata.</p>
              </div>
            )}
          </aside>
        </section>
      ) : null}

      <footer className="history-page-footer">
        <span>Viewing saved local reports</span>
        <div className="history-footer-actions">
          <Link className="history-button history-button--secondary" to="/workflow/run-monitor">
            <span aria-hidden="true">&lt;-</span>
            Back to Run Monitor
          </Link>
          {latestRun ? (
            <Link className="history-button history-button--primary" to={latestRunPath}>
              Open Latest Run
            </Link>
          ) : (
            <button className="history-button history-button--primary" type="button" disabled title={latestRunError || "No latest completed run is available."}>
              Open Latest Run
            </button>
          )}
        </div>
      </footer>
    </article>
  );
}
