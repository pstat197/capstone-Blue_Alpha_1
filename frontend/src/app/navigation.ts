export type AppSection = "workflow" | "monitor" | "results";

export type NavItem = {
  label: string;
  path: string;
  section: AppSection;
  description: string;
};

export const workflowNavItems: NavItem[] = [
  {
    label: "Welcome & Rules",
    path: "/workflow/welcome",
    section: "workflow",
    description: "Review Meridian CSV requirements before uploading data.",
  },
  {
    label: "New Analysis / Upload Data",
    path: "/workflow/upload",
    section: "workflow",
    description: "Start a new analysis draft and prepare the input CSV.",
  },
  {
    label: "KPI & Revenue Setup",
    path: "/workflow/kpi-revenue",
    section: "workflow",
    description: "Choose KPI fields and revenue-equivalent assumptions.",
  },
  {
    label: "Prior Grid Setup",
    path: "/workflow/prior-grid",
    section: "workflow",
    description: "Configure ROI prior mu, sigma, and distribution values.",
  },
  {
    label: "Structural Settings",
    path: "/workflow/structural-settings",
    section: "workflow",
    description: "Prepare structural sweep settings before a run starts.",
  },
  {
    label: "Review & Start Run",
    path: "/workflow/review-run",
    section: "workflow",
    description: "Validate the current configuration and launch the backend run.",
  },
];

export const monitorNavItem: NavItem = {
  label: "Run Monitor",
  path: "/workflow/run-monitor",
  section: "monitor",
  description: "Track submitted backend run progress from backend status.",
};

export const documentationNavItem: NavItem = {
  label: "Help / Documentation",
  path: "/documentation",
  section: "workflow",
  description: "Read dashboard methodology, interpretation guidance, and CSV requirements.",
};

export const resultNavItems: NavItem[] = [
  {
    label: "Results / Overview",
    path: "/results/overview",
    section: "results",
    description: "Completed-run summary, diagnostics context, and directional interpretation.",
  },
  {
    label: "Results / Prior Sensitivity",
    path: "/results/prior-sensitivity",
    section: "results",
    description: "Explore full-system prior response for completed outputs.",
  },
  {
    label: "Results / Prior vs Posterior",
    path: "/results/prior-vs-posterior",
    section: "results",
    description: "Compare prior assumptions against posterior evidence.",
  },
  {
    label: "Results / Scenario Explorer",
    path: "/results/scenario-explorer",
    section: "results",
    description: "Filter already-computed prior scenarios.",
  },
  {
    label: "Results / Model Structure",
    path: "/results/model-structure",
    section: "results",
    description: "Review adstock, saturation, and structural run evidence.",
  },
  {
    label: "Results / Run Audit & Diagnostics",
    path: "/results/run-audit-diagnostics",
    section: "results",
    description: "Inspect run setup, QC gates, and diagnostics outputs.",
  },
];

export const allNavItems: NavItem[] = [
  ...workflowNavItems,
  monitorNavItem,
  ...resultNavItems,
  documentationNavItem,
];
