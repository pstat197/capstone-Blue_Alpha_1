import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { KpiRevenuePage } from "../features/workflow/pages/KpiRevenuePage";
import { NewAnalysisUploadPage } from "../features/workflow/pages/NewAnalysisUploadPage";
import { PriorGridSetupPage } from "../features/workflow/pages/PriorGridSetupPage";
import { ReviewRunPage } from "../features/workflow/pages/ReviewRunPage";
import { StructuralSettingsPage } from "../features/workflow/pages/StructuralSettingsPage";
import { WelcomeRulesPage } from "../features/workflow/pages/WelcomeRulesPage";
import { RunMonitorPage } from "../features/run-monitor/pages/RunMonitorPage";
import { ModelStructurePage } from "../features/results/pages/ModelStructurePage";
import { OverviewPage } from "../features/results/pages/OverviewPage";
import { PriorSensitivityPage } from "../features/results/pages/PriorSensitivityPage";
import { PriorVsPosteriorPage } from "../features/results/pages/PriorVsPosteriorPage";
import { RunAuditDiagnosticsPage } from "../features/results/pages/RunAuditDiagnosticsPage";
import { ResultsHistoryPage } from "../features/results/pages/ResultsHistoryPage";
import { ScenarioExplorerPage } from "../features/results/pages/ScenarioExplorerPage";
import { DocumentationPage } from "../shared/DocumentationPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/workflow/welcome" replace /> },
      { path: "workflow/welcome", element: <WelcomeRulesPage /> },
      { path: "workflow/upload", element: <NewAnalysisUploadPage /> },
      { path: "workflow/kpi-revenue", element: <KpiRevenuePage /> },
      { path: "workflow/prior-grid", element: <PriorGridSetupPage /> },
      { path: "workflow/structural", element: <Navigate to="/workflow/structural-settings" replace /> },
      { path: "workflow/structural-settings", element: <StructuralSettingsPage /> },
      { path: "workflow/review", element: <Navigate to="/workflow/review-run" replace /> },
      { path: "workflow/review-run", element: <ReviewRunPage /> },
      { path: "workflow/run-monitor", element: <RunMonitorPage /> },
      { path: "runs/:runId/monitor", element: <RunMonitorPage /> },
      { path: "results/history", element: <ResultsHistoryPage /> },
      { path: "results/overview", element: <OverviewPage /> },
      { path: "results/:runId/overview", element: <OverviewPage /> },
      { path: "results/prior-sensitivity", element: <PriorSensitivityPage /> },
      { path: "results/prior-vs-posterior", element: <PriorVsPosteriorPage /> },
      { path: "results/scenario-explorer", element: <ScenarioExplorerPage /> },
      { path: "results/:runId/scenario-explorer", element: <ScenarioExplorerPage /> },
      { path: "results/model-structure", element: <ModelStructurePage /> },
      { path: "results/run-audit-diagnostics", element: <RunAuditDiagnosticsPage /> },
      { path: "documentation", element: <DocumentationPage /> },
      { path: "*", element: <Navigate to="/workflow/welcome" replace /> },
    ],
  },
]);
