import type { CsvProfile } from "../../../api/types";
import {
  defaultFullPriorGrid,
  priorGridModeStorageKey,
  priorGridStorageKey,
  revenuePerKpiStorageKey,
} from "./mockWorkflow";
import { isValidMediaChannel, normalizeChannelName } from "./channelRegistry";

export const activeProfileStorageKey = "adpilot.active_csv_profile";
export const kpiColumnStorageKey = "adpilot.kpi_column";
export const kpiTypeStorageKey = "adpilot.kpi_type";
export const revenueColumnStorageKey = "adpilot.revenue_column";
export const roiModeStorageKey = "adpilot.roi_mode";
export const revenueAssumptionSavedStorageKey = "adpilot.revenue_assumption_saved";
export const activeRunIdStorageKey = "adpilot.active_run_id";

export type KpiType = "revenue" | "non_revenue";
export type RoiMode = "direct_revenue_column" | "revenue_per_kpi_assumption";

export type ChannelPriorGrid = {
  enabled: boolean;
  use_custom: boolean;
  roi_mu_values: number[];
  roi_sigma_values: number[];
  roi_dist_values: string[];
};

export type ChannelPriorGrids = Record<string, ChannelPriorGrid>;

export type PriorRunLabel = {
  label: string;
  description: string;
  priorGridMode: string;
};

function sanitizeDetectedCandidates(candidates: Array<{ column: string; channel: string }> = []) {
  return candidates
    .map((item) => ({ ...item, channel: normalizeChannelName(item.channel) }))
    .filter((item) => isValidMediaChannel(item.channel));
}

function sanitizeProfile(profile: CsvProfile): CsvProfile {
  return {
    ...profile,
    storage_path: profile.storage_path ?? "",
    date_profile: profile.date_profile ?? {
      column: profile.detected.time_candidates?.[0] ?? null,
      date_min: null,
      date_max: null,
      valid_parse_rate: 0,
      inferred_frequency: null,
      status: profile.detected.time_candidates?.length ? "warning" : "missing",
      message: profile.detected.time_candidates?.length
        ? "Date column detected but date range could not be parsed."
        : "Date/time column missing",
    },
    channel_diagnostics: profile.channel_diagnostics ?? [],
    detected: {
      ...profile.detected,
      media_activity_candidates: sanitizeDetectedCandidates(profile.detected.media_activity_candidates ?? []),
      spend_channel_candidates: sanitizeDetectedCandidates(profile.detected.spend_channel_candidates ?? []),
      revenue_candidates: profile.detected.revenue_candidates ?? [],
      control_candidates: profile.detected.control_candidates ?? [],
      geo_candidates: profile.detected.geo_candidates ?? [],
      population_candidates: profile.detected.population_candidates ?? [],
    },
  };
}

export function readActiveProfile(): CsvProfile | null {
  const stored = window.localStorage.getItem(activeProfileStorageKey);
  if (!stored) {
    return null;
  }
  try {
    const parsed = JSON.parse(stored) as CsvProfile;
    return sanitizeProfile(parsed);
  } catch {
    return null;
  }
}

export function writeActiveProfile(profile: CsvProfile) {
  window.localStorage.setItem(activeProfileStorageKey, JSON.stringify(sanitizeProfile(profile)));
}

export function clearActiveProfile() {
  window.localStorage.removeItem(activeProfileStorageKey);
  clearDatasetSelections();
}

export function clearDatasetSelections() {
  [
    kpiColumnStorageKey,
    kpiTypeStorageKey,
    revenueColumnStorageKey,
    roiModeStorageKey,
    revenueAssumptionSavedStorageKey,
    revenuePerKpiStorageKey,
    priorGridStorageKey,
    priorGridModeStorageKey,
  ].forEach((key) => window.localStorage.removeItem(key));
}

export function detectedChannels(profile: CsvProfile | null): string[] {
  if (!profile) {
    return [];
  }
  return Array.from(
    new Set(
      profile.detected.spend_channel_candidates
        .map((item) => normalizeChannelName(item.channel))
        .filter((channel) => isValidMediaChannel(channel)),
    ),
  ).sort();
}

export function activePaidChannels(profile: CsvProfile | null): string[] {
  if (!profile) {
    return [];
  }
  const includedFromDiagnostics = (profile.channel_diagnostics ?? [])
    .filter((item) => item.include_in_model)
    .map((item) => normalizeChannelName(item.channel))
    .filter((channel) => isValidMediaChannel(channel));

  if (includedFromDiagnostics.length) {
    return Array.from(new Set(includedFromDiagnostics)).sort();
  }

  return detectedChannels(profile);
}

export function excludedChannelDiagnostics(profile: CsvProfile | null) {
  if (!profile) {
    return [];
  }
  return (profile.channel_diagnostics ?? [])
    .filter((item) => !item.include_in_model)
    .map((item) => ({ ...item, channel: normalizeChannelName(item.channel) }))
    .filter((item) => isValidMediaChannel(item.channel))
    .sort((a, b) => a.channel.localeCompare(b.channel));
}

export function makeDefaultChannelGrid(): ChannelPriorGrid {
  return {
    enabled: true,
    use_custom: false,
    roi_mu_values: defaultFullPriorGrid.muValues,
    roi_sigma_values: defaultFullPriorGrid.sigmaValues,
    roi_dist_values: defaultFullPriorGrid.distributions,
  };
}

export function makeChannelGrids(channels: string[]): ChannelPriorGrids {
  return Object.fromEntries(channels.map((channel) => [channel, makeDefaultChannelGrid()]));
}

export function readRevenuePerKpi(): number | null {
  if (window.localStorage.getItem(revenueAssumptionSavedStorageKey) !== "true") {
    return null;
  }
  const stored = window.localStorage.getItem(revenuePerKpiStorageKey);
  const parsed = stored ? Number(stored) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export function readKpiColumn(profile: CsvProfile | null): string {
  if (!profile) {
    return "";
  }
  const stored = window.localStorage.getItem(kpiColumnStorageKey);
  if (stored && profile.columns.some((column) => column.name === stored)) {
    return stored;
  }
  return profile.detected.kpi_candidates[0] ?? "";
}

export function readRevenueColumn(profile: CsvProfile | null): string {
  if (!profile) {
    return "";
  }
  const stored = window.localStorage.getItem(revenueColumnStorageKey);
  if (stored && profile.detected.revenue_candidates.includes(stored)) {
    return stored;
  }
  return profile.detected.revenue_candidates[0] ?? "";
}

export function readKpiType(profile: CsvProfile | null): KpiType {
  const stored = window.localStorage.getItem(kpiTypeStorageKey);
  if (stored === "revenue" || stored === "non_revenue") {
    return stored;
  }
  return profile?.detected.revenue_candidates.length ? "revenue" : "non_revenue";
}

export function readRoiMode(profile: CsvProfile | null): RoiMode {
  const stored = window.localStorage.getItem(roiModeStorageKey);
  if (stored === "direct_revenue_column" || stored === "revenue_per_kpi_assumption") {
    return stored;
  }
  return profile?.detected.revenue_candidates.length ? "direct_revenue_column" : "revenue_per_kpi_assumption";
}

export function profileHasBlockingErrors(profile: CsvProfile | null) {
  if (!profile) {
    return true;
  }
  return profile.validation_badges.some((badge) => {
    const lower = badge.label.toLowerCase();
    const optional = lower.includes("geo") || lower.includes("population");
    return badge.status === "error" && !optional;
  });
}

export function countRunsForGrid(grid: ChannelPriorGrid) {
  if (!grid.enabled) {
    return 0;
  }
  return grid.roi_mu_values.length * grid.roi_sigma_values.length * grid.roi_dist_values.length;
}

function numericValuesMatch(a: number[], b: number[]) {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

function stringValuesMatch(a: string[], b: string[]) {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

export function gridMatchesDefault(grid: ChannelPriorGrid) {
  return (
    grid.enabled &&
    !grid.use_custom &&
    numericValuesMatch(grid.roi_mu_values, defaultFullPriorGrid.muValues) &&
    numericValuesMatch(grid.roi_sigma_values, defaultFullPriorGrid.sigmaValues) &&
    stringValuesMatch(grid.roi_dist_values, defaultFullPriorGrid.distributions)
  );
}

export function getPriorRunLabel(channels: string[], channelPriorGrids: ChannelPriorGrids): PriorRunLabel {
  const selectedGrids = channels.map((channel) => channelPriorGrids[channel]).filter((grid) => grid?.enabled);
  const hasExcludedChannels = selectedGrids.length < channels.length;
  const hasCustomGrid = selectedGrids.some((grid) => !gridMatchesDefault(grid));

  if (hasExcludedChannels && hasCustomGrid) {
    return {
      label: "Custom Partial Prior Grid Run",
      description: "Executes selected channels with your custom prior settings.",
      priorGridMode: "Custom partial grid",
    };
  }
  if (hasExcludedChannels) {
    return {
      label: "Partial Prior Grid Run",
      description: "Executes only the selected channels.",
      priorGridMode: "Default grid for selected channels",
    };
  }
  if (hasCustomGrid) {
    return {
      label: "Custom Prior Grid Run",
      description: "Executes your per-channel prior settings.",
      priorGridMode: "Per-channel custom",
    };
  }
  return {
    label: "Default Prior Grid Run",
    description: "Executes all detected channels with the default prior grid.",
    priorGridMode: "Default prior grid",
  };
}
