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
    label: "Upload Data",
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
  path: "/help",
  section: "workflow",
  description: "Guides, docs & resources",
};

export const resultNavItems: NavItem[] = [
  {
    label: "Saved Results",
    path: "/results/history",
    section: "results",
    description: "Browse past runs & reports",
  },
  {
    label: "Overview",
    path: "/results/overview",
    section: "results",
    description: "Dashboard summary & key insights",
  },
  {
    label: "Prior Sensitivity",
    path: "/results/prior-sensitivity",
    section: "results",
    description: "Analyze prior sensitivity outputs",
  },
  {
    label: "Prior vs Posterior",
    path: "/results/prior-vs-posterior",
    section: "results",
    description: "Compare prior and posterior estimates",
  },
  {
    label: "Scenario Explorer",
    path: "/results/scenario-explorer",
    section: "results",
    description: "Explore scenarios & what-if analysis",
  },
  {
    label: "Model Structure",
    path: "/results/model-structure",
    section: "results",
    description: "Model components & configuration",
  },
  {
    label: "Run Audit & Diagnostics",
    path: "/results/run-audit-diagnostics",
    section: "results",
    description: "Audit logs & diagnostic results",
  },
];

export const allNavItems: NavItem[] = [
  ...workflowNavItems,
  monitorNavItem,
  ...resultNavItems,
];
