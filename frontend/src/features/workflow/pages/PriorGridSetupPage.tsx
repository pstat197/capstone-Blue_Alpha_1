import { useEffect, useMemo, useState } from "react";
import { ChannelLogo, displayChannelName } from "../data/channelRegistry";
import { baselinePriorStorageKey, defaultFullPriorGrid, priorGridModeStorageKey, priorGridStorageKey } from "../data/mockWorkflow";
import {
  type ChannelPriorGrid,
  type ChannelPriorGrids,
  activePaidChannels,
  countRunsForGrid,
  excludedChannelDiagnostics,
  makeChannelGrids,
  makeDefaultChannelGrid,
  readActiveProfile,
} from "../data/workflowState";
import { WorkflowScaffold } from "../components/WorkflowScaffold";

type ValueInputMode = "range" | "list";
type ChannelMode = "default" | "custom" | "excluded";

type RangeDraft = {
  start: string;
  end: string;
  increment: string;
};

type ChannelDraft = {
  mode: ChannelMode;
  muMode: ValueInputMode;
  sigmaMode: ValueInputMode;
  muRange: RangeDraft;
  sigmaRange: RangeDraft;
  muValues: number[];
  sigmaValues: number[];
  distributions: string[];
};

type BaselinePrior = {
  mu: number;
  sigma: number;
  distribution: string;
};

const defaultFullGrid = defaultFullPriorGrid;
const distributionOptions = ["LogNormal", "Normal", "HalfNormal"];
const defaultBaselinePrior: BaselinePrior = {
  mu: 1,
  sigma: 1,
  distribution: "LogNormal",
};
const baselineHelperText = "Baseline prior is the reference scenario used for delta ROI and sensitivity comparisons.";
const baselineRemovalWarning = "This value is part of the selected baseline. Choose a new baseline before removing it.";
const defaultMuRange = { start: "0.5", end: "5.0", increment: "0.5" };
const defaultSigmaRange = { start: "0.5", end: "1.5", increment: "0.5" };

function baselineRequirementText(baseline: BaselinePrior) {
  return `Baseline prior required: every included channel must include MU=${formatNumber(baseline.mu)}, Sigma=${formatNumber(baseline.sigma)}, ${baseline.distribution}.`;
}

function missingBaselineText(channel: string, baseline: BaselinePrior, grid?: ChannelPriorGrid) {
  const gridLabel = grid?.use_custom ? "custom grid" : "active grid";
  return `Baseline prior is missing from ${displayChannelName(channel)}'s ${gridLabel}. Add MU=${formatNumber(baseline.mu)}, Sigma=${formatNumber(baseline.sigma)}, ${baseline.distribution} or choose another baseline before continuing.`;
}

function readBaselinePrior(): BaselinePrior {
  const stored = window.localStorage.getItem(baselinePriorStorageKey);
  if (!stored) {
    return defaultBaselinePrior;
  }
  try {
    const parsed = JSON.parse(stored) as Partial<BaselinePrior>;
    const mu = typeof parsed.mu === "number" && Number.isFinite(parsed.mu) && parsed.mu > 0 ? parsed.mu : defaultBaselinePrior.mu;
    const sigma = typeof parsed.sigma === "number" && Number.isFinite(parsed.sigma) && parsed.sigma > 0 ? parsed.sigma : defaultBaselinePrior.sigma;
    const distribution = parsed.distribution && distributionOptions.includes(parsed.distribution) ? parsed.distribution : defaultBaselinePrior.distribution;
    return { mu, sigma, distribution };
  } catch {
    return defaultBaselinePrior;
  }
}

function writeBaselinePrior(baseline: BaselinePrior) {
  window.localStorage.setItem(baselinePriorStorageKey, JSON.stringify(baseline));
}
function normalizeStoredGrids(raw: unknown, channels: string[]): ChannelPriorGrids {
  const fallback = makeChannelGrids(channels);
  const parsed = raw && typeof raw === "object" ? (raw as ChannelPriorGrids) : {};
  return Object.fromEntries(
    channels.map((channel) => [
      channel,
      {
        ...fallback[channel],
        ...(parsed[channel] || {}),
      },
    ]),
  );
}

function hydrateChannelGrids(channels: string[]): ChannelPriorGrids {
  const stored = window.localStorage.getItem(priorGridStorageKey);
  if (!stored) {
    return normalizeStoredGrids({}, channels);
  }

  try {
    return normalizeStoredGrids(JSON.parse(stored), channels);
  } catch {
    return normalizeStoredGrids({}, channels);
  }
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : String(value);
}

function formatValues(values: Array<number | string>) {
  return values.map((value) => (typeof value === "number" ? formatNumber(value) : value)).join(", ");
}

function parseNumber(value: string) {
  const parsed = Number(value.trim());
  return Number.isFinite(parsed) && parsed > 0 ? Number(parsed.toFixed(6)) : null;
}

function buildRange(startRaw: string, endRaw: string, incrementRaw: string) {
  const start = parseNumber(startRaw);
  const end = parseNumber(endRaw);
  const increment = parseNumber(incrementRaw);
  if (start === null || end === null || increment === null || end < start) {
    return [];
  }

  const values: number[] = [];
  for (let value = start; value <= end + 1e-9; value += increment) {
    values.push(Number(value.toFixed(6)));
  }
  return values;
}

function includesNumber(values: number[], required: number) {
  return values.some((value) => Math.abs(value - required) <= 1e-9);
}

function addNumber(values: number[], raw: string) {
  const value = parseNumber(raw);
  if (value === null) {
    return values;
  }
  return Array.from(new Set([...values, value])).sort((a, b) => a - b);
}

function removeNumber(values: number[], value: number) {
  return values.filter((item) => item !== value);
}

function gridIncludesBaseline(grid: ChannelPriorGrid, baseline: BaselinePrior) {
  if (!grid.enabled) {
    return true;
  }
  return (
    includesNumber(grid.roi_mu_values, baseline.mu) &&
    includesNumber(grid.roi_sigma_values, baseline.sigma) &&
    grid.roi_dist_values.includes(baseline.distribution)
  );
}

function draftIncludesBaseline(draft: ChannelDraft, baseline: BaselinePrior) {
  return gridIncludesBaseline(gridFromDraft(draft), baseline);
}

function gridStatus(grid: ChannelPriorGrid): ChannelMode {
  if (!grid.enabled) {
    return "excluded";
  }
  return grid.use_custom ? "custom" : "default";
}

function draftFromGrid(grid: ChannelPriorGrid): ChannelDraft {
  const mode = grid.enabled ? gridStatus(grid) : "default";
  return {
    mode,
    muMode: mode === "custom" ? "list" : "range",
    sigmaMode: mode === "custom" ? "list" : "range",
    muRange: defaultMuRange,
    sigmaRange: defaultSigmaRange,
    muValues: grid.roi_mu_values.length ? grid.roi_mu_values : defaultFullGrid.muValues,
    sigmaValues: grid.roi_sigma_values.length ? grid.roi_sigma_values : defaultFullGrid.sigmaValues,
    distributions: grid.roi_dist_values.length ? grid.roi_dist_values : defaultFullGrid.distributions,
  };
}

function gridFromDraft(draft: ChannelDraft): ChannelPriorGrid {
  if (draft.mode === "excluded") {
    return {
      ...makeDefaultChannelGrid(),
      enabled: false,
      use_custom: false,
    };
  }

  if (draft.mode === "default") {
    return makeDefaultChannelGrid();
  }

  return {
    enabled: true,
    use_custom: true,
    roi_mu_values: draft.muMode === "range" ? buildRange(draft.muRange.start, draft.muRange.end, draft.muRange.increment) : draft.muValues,
    roi_sigma_values: draft.sigmaMode === "range" ? buildRange(draft.sigmaRange.start, draft.sigmaRange.end, draft.sigmaRange.increment) : draft.sigmaValues,
    roi_dist_values: draft.distributions.length ? draft.distributions : ["LogNormal"],
  };
}

function modeConfigPreview(channelGrids: ChannelPriorGrids, channels: string[], baseline: BaselinePrior, baselineConfirmed: boolean) {
  return {
    mode: "per_channel_custom",
    baseline: {
      roi_mu: baseline.mu,
      roi_sigma: baseline.sigma,
      roi_dist: baseline.distribution,
      confirmed: baselineConfirmed,
    },
    default_grid: {
      mu: { start: 0.5, end: 5.0, increment: 0.5, count: defaultFullGrid.muValues.length },
      sigma: { values: defaultFullGrid.sigmaValues, count: defaultFullGrid.sigmaValues.length },
      distribution: defaultFullGrid.distributions,
    },
    channels: Object.fromEntries(
      channels.map((channel) => {
        const grid = channelGrids[channel];
        if (!grid.enabled) {
          return [channel, { status: "excluded" }];
        }
        if (!grid.use_custom) {
          return [channel, { status: "default" }];
        }
        return [
          channel,
          {
            status: "custom",
            mu: grid.roi_mu_values,
            sigma: grid.roi_sigma_values,
            distribution: grid.roi_dist_values,
          },
        ];
      }),
    ),
  };
}

function excludedReason(status: string) {
  if (status === "inactive_all_zero") {
    return "Inactive / all-zero spend and media activity.";
  }
  if (status === "not_eligible_paid_media") {
    return "Not eligible as paid media for model setup.";
  }
  return "Excluded from model setup.";
}

function ValueChips({ baselineValue, values }: { baselineValue?: number; values: number[] }) {
  return (
    <div className="prior-value-chips">
      {values.map((value) => {
        const isBaseline = baselineValue !== undefined && Math.abs(value - baselineValue) <= 1e-9;
        return (
          <span
            className={isBaseline ? "prior-value-chip prior-value-chip--baseline" : "prior-value-chip"}
            key={value}
            title={isBaseline ? baselineHelperText : undefined}
          >
            {formatNumber(value)}
            {isBaseline ? " baseline" : ""}
          </span>
        );
      })}
    </div>
  );
}

function RangeFields({
  range,
  onChange,
}: {
  range: RangeDraft;
  onChange: (range: RangeDraft) => void;
}) {
  return (
    <div className="prior-range-fields">
      {(["start", "end", "increment"] as const).map((field) => (
        <label key={field}>
          <span>{field === "start" ? "Start" : field === "end" ? "End" : "Increment"}</span>
          <input value={range[field]} onChange={(event) => onChange({ ...range, [field]: event.target.value })} />
        </label>
      ))}
    </div>
  );
}

function CustomListInput({
  baselineValue,
  label,
  values,
  onChange,
  onBlockedBaselineRemove,
}: {
  baselineValue?: number;
  label: string;
  values: number[];
  onChange: (values: number[]) => void;
  onBlockedBaselineRemove?: () => void;
}) {
  const [entry, setEntry] = useState("");
  const isEmpty = values.length === 0;

  const commitEntry = () => {
    const nextValues = entry
      .split(",")
      .reduce((acc, token) => addNumber(acc, token), values);
    onChange(nextValues);
    setEntry("");
  };

  return (
    <>
      <div className={isEmpty ? "prior-chip-input prior-chip-input--invalid" : "prior-chip-input"}>
        {values.map((value) => {
          const isBaseline = baselineValue !== undefined && Math.abs(value - baselineValue) <= 1e-9;
          return (
            <button
              className={isBaseline ? "prior-chip prior-chip--locked" : "prior-chip"}
              key={value}
              title={isBaseline ? baselineHelperText : undefined}
              type="button"
              onClick={() => {
                if (isBaseline) {
                  onBlockedBaselineRemove?.();
                  return;
                }
                onChange(removeNumber(values, value));
              }}
            >
              {formatNumber(value)}
              {isBaseline ? " baseline" : <span aria-hidden="true">×</span>}
            </button>
          );
        })}
        <input
          aria-label={`Add ${label}`}
          value={entry}
          onBlur={commitEntry}
          onChange={(event) => setEntry(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === ",") {
              event.preventDefault();
              commitEntry();
            }
          }}
          placeholder="Add value and press Enter"
        />
      </div>
      {isEmpty ? <p className="prior-validation-text">Add at least one numeric value before continuing.</p> : null}
      {baselineValue !== undefined ? <p className="prior-helper-text">{baselineHelperText}</p> : null}
    </>
  );
}

function DefaultGridBuilder({
  label,
  helper,
  mode,
  range,
  customValues,
  onModeChange,
  onRangeChange,
  onCustomValuesChange,
}: {
  label: string;
  helper: string;
  mode: ValueInputMode;
  range: RangeDraft;
  customValues: number[];
  onModeChange: (mode: ValueInputMode) => void;
  onRangeChange: (range: RangeDraft) => void;
  onCustomValuesChange: (values: number[]) => void;
}) {
  const values = mode === "range" ? buildRange(range.start, range.end, range.increment) : customValues;

  return (
    <section className="prior-builder-section">
      <div className="prior-builder-heading">
        <div>
          <h4>{label}</h4>
          <p>{label === "MU Values" ? "Control the prior mean range" : "Control the prior spread range"}</p>
        </div>
      </div>
      <div className="prior-segmented-control" aria-label={`${label} input mode`}>
        <button className={mode === "range" ? "is-active" : ""} type="button" onClick={() => onModeChange("range")}>Range</button>
        <button className={mode === "list" ? "is-active" : ""} type="button" onClick={() => onModeChange("list")}>Custom List</button>
      </div>
      {mode === "range" ? (
        <>
          <RangeFields range={range} onChange={onRangeChange} />
          <span className="prior-generated-label">Generated Values ({values.length})</span>
          <ValueChips values={values} />
        </>
      ) : (
        <CustomListInput label={label} values={customValues} onChange={onCustomValuesChange} />
      )}
      <p className="prior-helper-text">{helper}</p>
    </section>
  );
}

function DrawerValueEditor({
  baselineValue,
  label,
  mode,
  range,
  values,
  onModeChange,
  onRangeChange,
  onValuesChange,
  onBlockedBaselineRemove,
}: {
  baselineValue: number;
  label: string;
  mode: ValueInputMode;
  range: RangeDraft;
  values: number[];
  onModeChange: (mode: ValueInputMode) => void;
  onRangeChange: (range: RangeDraft) => void;
  onValuesChange: (values: number[]) => void;
  onBlockedBaselineRemove: () => void;
}) {
  const displayedValues = mode === "range" ? buildRange(range.start, range.end, range.increment) : values;

  return (
    <section className="prior-drawer-section">
      <div className="prior-value-editor__header">
        <strong>{label}</strong>
        <span>{displayedValues.length} values</span>
      </div>
      <div className="prior-editor-tabs" aria-label={`${label} input modes`}>
        <button className={mode === "range" ? "prior-editor-tab prior-editor-tab--active" : "prior-editor-tab"} type="button" onClick={() => onModeChange("range")}>Range</button>
        <button className={mode === "list" ? "prior-editor-tab prior-editor-tab--active" : "prior-editor-tab"} type="button" onClick={() => onModeChange("list")}>Custom List</button>
      </div>
      {mode === "range" ? (
        <>
          <RangeFields range={range} onChange={onRangeChange} />
          <ValueChips baselineValue={baselineValue} values={displayedValues} />
        </>
      ) : (
        <CustomListInput
          baselineValue={baselineValue}
          label={label}
          values={values}
          onBlockedBaselineRemove={onBlockedBaselineRemove}
          onChange={onValuesChange}
        />
      )}
      <p className="prior-helper-text">Custom List supports irregular values without fixed increments.</p>
    </section>
  );
}

function DistributionCards({
  baselineDistribution,
  selected,
  onChange,
  onBlockedBaselineRemove,
  compact = false,
}: {
  baselineDistribution: string;
  selected: string[];
  onChange: (selected: string[]) => void;
  onBlockedBaselineRemove: () => void;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "prior-distribution-grid prior-distribution-grid--compact" : "prior-distribution-grid"}>
      {distributionOptions.map((distribution) => (
        <label className="prior-distribution-card" key={distribution} title={distribution === baselineDistribution ? baselineHelperText : undefined}>
          <input
            checked={selected.includes(distribution)}
            onChange={(event) => {
              if (!event.target.checked && distribution === baselineDistribution) {
                onBlockedBaselineRemove();
                return;
              }
              const next = event.target.checked
                ? Array.from(new Set([...selected, distribution]))
                : selected.filter((value) => value !== distribution);
              onChange(next.length ? next : [baselineDistribution]);
            }}
            type="checkbox"
          />
          <span aria-hidden="true" className="prior-distribution-curve" />
          <strong>
            {distribution}
            {distribution === baselineDistribution ? <span className="prior-baseline-tag"> baseline</span> : null}
          </strong>
          {!compact ? (
            <small>
              {distribution === "LogNormal"
                ? "Positive values, right-skewed"
                : distribution === "Normal"
                  ? "Symmetric around mean"
                  : "Positive values, half-normal"}
            </small>
          ) : null}
        </label>
      ))}
    </div>
  );
}

function BaselinePriorCard({
  baseline,
  confirmed,
  onChange,
  onConfirm,
}: {
  baseline: BaselinePrior;
  confirmed: boolean;
  onChange: (baseline: BaselinePrior) => void;
  onConfirm: () => void;
}) {
  const updateNumeric = (key: "mu" | "sigma", raw: string) => {
    const parsed = parseNumber(raw);
    if (parsed !== null) {
      onChange({ ...baseline, [key]: parsed });
    }
  };

  return (
    <section className="content-panel prior-baseline-panel">
      <div className="prior-baseline-heading">
        <div>
          <span className="eyebrow">Baseline Prior for Comparison</span>
          <p>{baselineHelperText}</p>
        </div>
        <span className={confirmed ? "prior-baseline-confirm prior-baseline-confirm--ok" : "prior-baseline-confirm"}>
          {confirmed ? "Confirmed" : "Needs confirmation"}
        </span>
      </div>
      <div className="prior-baseline-fields">
        <label>
          <span>MU baseline</span>
          <input
            defaultValue={formatNumber(baseline.mu)}
            inputMode="decimal"
            onBlur={(event) => updateNumeric("mu", event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                updateNumeric("mu", event.currentTarget.value);
                event.currentTarget.blur();
              }
            }}
          />
        </label>
        <label>
          <span>Sigma baseline</span>
          <input
            defaultValue={formatNumber(baseline.sigma)}
            inputMode="decimal"
            onBlur={(event) => updateNumeric("sigma", event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                updateNumeric("sigma", event.currentTarget.value);
                event.currentTarget.blur();
              }
            }}
          />
        </label>
        <label>
          <span>Distribution baseline</span>
          <select
            value={baseline.distribution}
            onChange={(event) => onChange({ ...baseline, distribution: event.target.value })}
          >
            {distributionOptions.map((distribution) => (
              <option key={distribution} value={distribution}>{distribution}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={onConfirm}>Confirm Baseline</button>
      </div>
    </section>
  );
}

export function PriorGridSetupPage() {
  const profile = useMemo(() => readActiveProfile(), []);
  const channels = useMemo(() => activePaidChannels(profile), [profile]);
  const excludedChannels = useMemo(() => excludedChannelDiagnostics(profile), [profile]);
  const [channelGrids, setChannelGrids] = useState<ChannelPriorGrids>(() => hydrateChannelGrids(channels));
  const [activeChannel, setActiveChannel] = useState(() => channels[0] ?? "");
  const [channelDraft, setChannelDraft] = useState<ChannelDraft>(() => draftFromGrid(hydrateChannelGrids(channels)[channels[0] ?? ""] ?? makeDefaultChannelGrid()));
  const [baselinePrior, setBaselinePrior] = useState<BaselinePrior>(() => readBaselinePrior());
  const [baselineConfirmed, setBaselineConfirmed] = useState(() => window.localStorage.getItem(`${baselinePriorStorageKey}.confirmed`) === "true");
  const [baselineRemoveMessage, setBaselineRemoveMessage] = useState("");

  useEffect(() => {
    if (activeChannel && channelGrids[activeChannel]) {
      setChannelDraft(draftFromGrid(channelGrids[activeChannel]));
    }
  }, [activeChannel, channelGrids]);

  const persistGrids = (next: ChannelPriorGrids) => {
    setChannelGrids(next);
    window.localStorage.setItem(priorGridStorageKey, JSON.stringify(next));
    window.localStorage.setItem(priorGridModeStorageKey, "custom");
  };

  const updateBaseline = (next: BaselinePrior) => {
    setBaselinePrior(next);
    writeBaselinePrior(next);
    setBaselineConfirmed(false);
    window.localStorage.setItem(`${baselinePriorStorageKey}.confirmed`, "false");
  };

  const confirmBaseline = () => {
    setBaselineConfirmed(true);
    window.localStorage.setItem(`${baselinePriorStorageKey}.confirmed`, "true");
  };

  const updateChannel = (channel: string, patch: Partial<ChannelPriorGrid>) => {
    persistGrids({
      ...channelGrids,
      [channel]: {
        ...channelGrids[channel],
        ...patch,
      },
    });
  };

  const setChannelState = (channel: string, state: ChannelMode) => {
    setActiveChannel(channel);
    if (state === "excluded") {
      updateChannel(channel, { enabled: false, use_custom: false });
      return;
    }
    updateChannel(channel, state === "default" ? makeDefaultChannelGrid() : { enabled: true, use_custom: true });
  };

  const resetToDefaults = () => {
    const defaults = makeChannelGrids(channels);
    persistGrids(defaults);
  };

  const applyChannelDraft = () => {
    const nextGrid = gridFromDraft(channelDraft);
    if (!gridIncludesBaseline(nextGrid, baselinePrior)) {
      return;
    }
    if (activeChannel) {
      updateChannel(activeChannel, {
        ...nextGrid,
        enabled: channelGrids[activeChannel]?.enabled ?? nextGrid.enabled,
      });
    }
  };

  const withBaseline = (grid: ChannelPriorGrid): ChannelPriorGrid => ({
    ...grid,
    roi_mu_values: includesNumber(grid.roi_mu_values, baselinePrior.mu)
      ? grid.roi_mu_values
      : addNumber(grid.roi_mu_values, String(baselinePrior.mu)),
    roi_sigma_values: includesNumber(grid.roi_sigma_values, baselinePrior.sigma)
      ? grid.roi_sigma_values
      : addNumber(grid.roi_sigma_values, String(baselinePrior.sigma)),
    roi_dist_values: grid.roi_dist_values.includes(baselinePrior.distribution)
      ? grid.roi_dist_values
      : [...grid.roi_dist_values, baselinePrior.distribution],
  });

  const addBaselineToChannel = (channel: string) => {
    const grid = channelGrids[channel];
    if (!grid || !grid.use_custom) {
      return;
    }
    updateChannel(channel, withBaseline(grid));
  };

  const addBaselineToAllCustomGrids = () => {
    persistGrids(
      Object.fromEntries(
        channels.map((channel) => {
          const grid = channelGrids[channel];
          return [channel, grid.use_custom ? withBaseline(grid) : grid];
        }),
      ),
    );
  };

  const customModeInvalid = channels.some((channel) => {
    const grid = channelGrids[channel];
    return grid.enabled && grid.use_custom && (!grid.roi_mu_values.length || !grid.roi_sigma_values.length || !grid.roi_dist_values.length);
  });
  const baselineInvalidChannels = channels.filter((channel) => !gridIncludesBaseline(channelGrids[channel], baselinePrior));
  const baselineInvalid = baselineInvalidChannels.length > 0;
  const activeDraftBaselineInvalid = channelDraft.mode === "custom" && !draftIncludesBaseline(channelDraft, baselinePrior);
  const baselineConfirmationInvalid = !baselineConfirmed;

  const perChannelRows = channels.map((channel) => ({
    channel,
    grid: channelGrids[channel],
    runs: countRunsForGrid(channelGrids[channel]),
  }));
  const totalRuns = perChannelRows.reduce((total, row) => total + row.runs, 0);
  const preview = useMemo(
    () => modeConfigPreview(channelGrids, channels, baselinePrior, baselineConfirmed),
    [baselineConfirmed, baselinePrior, channelGrids, channels],
  );

  if (!profile || !channels.length) {
    return (
      <WorkflowScaffold
        title="Prior Grid Setup"
        summary="Define default and per-channel prior grids for the production sensitivity audit."
        primaryActionDisabled
        nextHelperText={profile ? "No channels detected." : "Upload and profile a CSV first."}
      >
        <section className="content-panel prior-default-panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Generic defaults</span>
              <h3>{profile ? "No media spend channels detected" : "Upload and profile a CSV first"}</h3>
              <p>Estimated runs are unavailable until spend channels are detected from the active dataset.</p>
            </div>
            <span className="subtle-chip">Estimated runs: 0</span>
          </div>
          <div className="prior-default-summary">
            <div><strong>MU values</strong><span>0.5 to 5.0 by 0.5</span><small>{defaultFullGrid.muValues.length} values</small></div>
            <div><strong>Sigma values</strong><span>{formatValues(defaultFullGrid.sigmaValues)}</span><small>{defaultFullGrid.sigmaValues.length} values</small></div>
            <div><strong>Distribution</strong><span>{formatValues(defaultFullGrid.distributions)}</span><small>{defaultFullGrid.distributions.length} distribution</small></div>
          </div>
        </section>
      </WorkflowScaffold>
    );
  }

  return (
    <WorkflowScaffold
      title="Prior Grid Setup"
      summary="Define default and per-channel prior grids for the production sensitivity audit."
      primaryActionDisabled={customModeInvalid || baselineInvalid || baselineConfirmationInvalid}
      nextHelperText={
        baselineConfirmationInvalid
          ? "Confirm the baseline prior before continuing."
          : baselineInvalid
            ? "Add the required baseline prior to every included channel."
            : undefined
      }
    >
      <div className="prior-warning">Custom grids may increase run time and should be reviewed before production runs.</div>
      {baselineInvalid ? (
        <div className="prior-warning prior-warning--error" role="alert">
          {missingBaselineText(baselineInvalidChannels[0], baselinePrior, channelGrids[baselineInvalidChannels[0]])}
          <span>
            Missing baseline in: {baselineInvalidChannels.map((channel) => displayChannelName(channel)).join(", ")}.
          </span>
          <div className="prior-warning-actions">
            {channelGrids[baselineInvalidChannels[0]]?.use_custom ? (
              <button type="button" onClick={() => addBaselineToChannel(baselineInvalidChannels[0])}>Add baseline to this channel</button>
            ) : null}
            <button type="button" onClick={addBaselineToAllCustomGrids}>Add baseline to all custom grids</button>
            <button
              type="button"
              onClick={() => {
                setBaselineConfirmed(false);
                window.localStorage.setItem(`${baselinePriorStorageKey}.confirmed`, "false");
              }}
            >
              Choose different baseline
            </button>
          </div>
        </div>
      ) : null}
      <div className="prior-custom-layout">
            <main className="prior-custom-main">
              <section className="content-panel prior-default-panel">
                <div className="section-title-row">
                  <div>
                    <span className="eyebrow">Default Full Grid (Baseline)</span>
                  </div>
                </div>
                <div className="prior-default-summary">
                  <div>
                    <strong>MU values</strong>
                    <span>0.5 to 5.0 by 0.5</span>
                    <small>{defaultFullGrid.muValues.length} values</small>
                  </div>
                  <div>
                    <strong>Sigma values</strong>
                    <span>{formatValues(defaultFullGrid.sigmaValues)}</span>
                    <small>{defaultFullGrid.sigmaValues.length} values</small>
                  </div>
                  <div>
                    <strong>Distribution</strong>
                    <span>{formatValues(defaultFullGrid.distributions)}</span>
                    <small>{defaultFullGrid.distributions.length} distribution</small>
                  </div>
                </div>
              </section>

              <BaselinePriorCard
                baseline={baselinePrior}
                confirmed={baselineConfirmed}
                onChange={updateBaseline}
                onConfirm={confirmBaseline}
              />

              <section className="content-panel prior-channel-panel">
                <div className="section-title-row">
                  <div>
                    <span className="eyebrow">Per-Channel Prior Grid Configuration</span>
                    <h3>{channels.length} active paid channels</h3>
                    <p>Click a channel to edit in the drawer.</p>
                  </div>
                  <div className="prior-table-actions">
                    <button type="button" onClick={() => channels.forEach((channel) => setChannelState(channel, "default"))}>Select All</button>
                    <button type="button" onClick={() => channels.forEach((channel) => setChannelState(channel, "excluded"))}>Clear All</button>
                    <button type="button" onClick={resetToDefaults}>Reset to Defaults</button>
                  </div>
                </div>

                {excludedChannels.length ? (
                  <div className="prior-excluded-note" role="status">
                    <strong>
                      {excludedChannels.length} detected channel{excludedChannels.length === 1 ? " was" : "s were"} excluded from prior grid setup:{" "}
                      {excludedChannels.map((item) => displayChannelName(item.channel)).join(", ")}.
                    </strong>
                    <span>{excludedReason(excludedChannels[0].status)}</span>
                  </div>
                ) : null}

                <div className="prior-channel-table" role="table" aria-label="Channel prior grid configuration">
                  <div className="prior-channel-header" role="row">
                    <span>Channel</span>
                    <span>Status</span>
                    <span>MU Values</span>
                    <span>Sigma Values</span>
                    <span>Distribution(s)</span>
                    <span />
                  </div>
                  {perChannelRows.map(({ channel, grid }) => (
                    <div
                      className={activeChannel === channel ? "prior-channel-row prior-channel-row--active" : "prior-channel-row"}
                      key={channel}
                      onClick={() => setActiveChannel(channel)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setActiveChannel(channel);
                        }
                      }}
                      role="row"
                      tabIndex={0}
                    >
                      <span className="prior-channel-name">
                        <input
                          aria-label={`Include ${channel}`}
                          checked={grid.enabled}
                          onChange={(event) => {
                            event.stopPropagation();
                            setChannelState(channel, event.target.checked ? "default" : "excluded");
                          }}
                          onClick={(event) => event.stopPropagation()}
                          type="checkbox"
                        />
                        <ChannelLogo channel={channel} />
                        <strong>{displayChannelName(channel)}</strong>
                      </span>
                      <span className={`prior-status prior-status--${gridStatus(grid)}`}>
                        {gridStatus(grid) === "custom" ? "Custom" : gridStatus(grid) === "default" ? "Default" : "Excluded"}
                      </span>
                      <span>
                        {grid.enabled ? (grid.use_custom ? formatValues(grid.roi_mu_values) : "0.5-5.0 by 0.5") : "-"}
                        <small>{grid.enabled ? `${grid.roi_mu_values.length} values` : ""}</small>
                      </span>
                      <span>
                        {grid.enabled ? formatValues(grid.roi_sigma_values) : "-"}
                        <small>{grid.enabled ? `${grid.roi_sigma_values.length} values` : ""}</small>
                      </span>
                      <span>
                        {grid.enabled ? formatValues(grid.roi_dist_values) : "-"}
                        <small>{grid.enabled ? `${grid.roi_dist_values.length} selected` : ""}</small>
                      </span>
                      <span className="prior-row-chevron">›</span>
                    </div>
                  ))}
                </div>
              </section>
            </main>

            <aside className="prior-channel-drawer" aria-label={`Edit Channel: ${displayChannelName(activeChannel)}`}>
              <div className="prior-drawer-header">
                <h3>Edit Channel: {displayChannelName(activeChannel)}</h3>
                <button aria-label="Close editor" type="button" onClick={() => setActiveChannel(activeChannel)}>×</button>
              </div>
              <div className="prior-drawer-mode-toggle">
                {(["default", "custom"] as ChannelMode[]).map((state) => (
                  <button
                    className={channelDraft.mode === state ? "is-active" : ""}
                    key={state}
                    type="button"
                    onClick={() => setChannelDraft((current) => ({ ...current, mode: state }))}
                  >
                    {state === "default" ? "Use Default" : "Custom Grid"}
                  </button>
                ))}
              </div>
              {baselineRemoveMessage ? <p className="prior-validation-text">{baselineRemoveMessage}</p> : null}

              {channelDraft.mode === "custom" ? (
                <>
                  <DrawerValueEditor
                    baselineValue={baselinePrior.mu}
                    label="MU Values"
                    mode={channelDraft.muMode}
                    range={channelDraft.muRange}
                    values={channelDraft.muValues}
                    onBlockedBaselineRemove={() => setBaselineRemoveMessage(baselineRemovalWarning)}
                    onModeChange={(nextMode) => setChannelDraft((current) => ({ ...current, muMode: nextMode }))}
                    onRangeChange={(range) => setChannelDraft((current) => ({ ...current, muRange: range }))}
                    onValuesChange={(values) => setChannelDraft((current) => ({ ...current, muValues: values }))}
                  />
                  <DrawerValueEditor
                    baselineValue={baselinePrior.sigma}
                    label="Sigma Values"
                    mode={channelDraft.sigmaMode}
                    range={channelDraft.sigmaRange}
                    values={channelDraft.sigmaValues}
                    onBlockedBaselineRemove={() => setBaselineRemoveMessage(baselineRemovalWarning)}
                    onModeChange={(nextMode) => setChannelDraft((current) => ({ ...current, sigmaMode: nextMode }))}
                    onRangeChange={(range) => setChannelDraft((current) => ({ ...current, sigmaRange: range }))}
                    onValuesChange={(values) => setChannelDraft((current) => ({ ...current, sigmaValues: values }))}
                  />
                  <section className="prior-drawer-section">
                    <div className="prior-value-editor__header">
                      <strong>Distribution(s)</strong>
                      <span>{channelDraft.distributions.length} selected</span>
                    </div>
                    <DistributionCards
                      baselineDistribution={baselinePrior.distribution}
                      compact
                      selected={channelDraft.distributions}
                      onBlockedBaselineRemove={() => setBaselineRemoveMessage(baselineRemovalWarning)}
                      onChange={(distributions) => setChannelDraft((current) => ({ ...current, distributions }))}
                    />
                    <p className="prior-helper-text">{baselineHelperText}</p>
                  </section>
                  {activeDraftBaselineInvalid ? (
                    <p className="prior-validation-text">{baselineRequirementText(baselinePrior)}</p>
                  ) : null}
                </>
              ) : (
                <p className="prior-drawer-empty">
                  This channel will inherit the default full grid unless you switch to Custom Grid.
                </p>
              )}

              <div className="prior-drawer-actions">
                <button type="button" onClick={() => setChannelDraft(draftFromGrid(channelGrids[activeChannel]))}>Cancel</button>
                <button
                  disabled={
                    channelDraft.mode === "custom" &&
                    (
                      !gridFromDraft(channelDraft).roi_mu_values.length ||
                      !gridFromDraft(channelDraft).roi_sigma_values.length ||
                      activeDraftBaselineInvalid
                    )
                  }
                  type="button"
                  onClick={applyChannelDraft}
                >
                  Apply Changes
                </button>
              </div>
            </aside>

            <aside className="prior-side-panel">
              <section className="content-panel prior-estimate-panel">
                <div className="prior-panel-heading">
                  <h3>Estimated Runs</h3>
                  <strong>{totalRuns}</strong>
                </div>
                <div className="prior-run-calculation">
                  {perChannelRows.map(({ channel, grid, runs }) => (
                    <div className={grid.enabled ? "prior-calc-row" : "prior-calc-row prior-calc-row--muted"} key={channel}>
                      <span>{displayChannelName(channel)}</span>
                      <strong>{runs}</strong>
                    </div>
                  ))}
                  <div className="prior-total-line">
                    <span>Total</span>
                    <strong>{totalRuns}</strong>
                  </div>
                </div>
              </section>

              <section className="content-panel prior-config-panel">
                <div className="prior-config-heading">
                  <h3>Configuration Preview</h3>
                  <span className="subtle-chip">JSON</span>
                </div>
                <pre className="config-preview prior-config-preview">{JSON.stringify(preview, null, 2)}</pre>
              </section>

              <section className="content-panel prior-explainer-card">
                <span className="prior-explainer-icon" aria-hidden="true">✧</span>
                <div>
                  <h3>Editing Behavior</h3>
                  <p>Click any channel in the list to open the editor drawer. Your changes are previewed in real time and applied when you save.</p>
                </div>
              </section>
            </aside>
          </div>
    </WorkflowScaffold>
  );
}
