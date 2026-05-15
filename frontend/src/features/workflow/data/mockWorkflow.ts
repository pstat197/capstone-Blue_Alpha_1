export const defaultFullPriorGrid = {
  muValues: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
  sigmaValues: [0.5, 1.0, 1.5],
  distributions: ["LogNormal"],
};

export const structuralAssumptions = {
  alphaM: 0.3,
  ecM: 0.5,
  slopeM: 1.2,
  maxLag: 4,
  adstockDecay: "geometric",
};

export const structuralSettingsStorageKey = "adpilot.structural_profile";

export const samplerSettings = {
  nChains: 4,
  nAdapt: 700,
  nBurnin: 500,
  nKeep: 300,
  seed: 0,
  parallelWorkers: 4,
};

export const revenuePerKpiStorageKey = "adpilot.revenue_per_kpi";
export const priorGridStorageKey = "adpilot.channel_prior_grids";
export const priorGridModeStorageKey = "adpilot.prior_grid_mode";
