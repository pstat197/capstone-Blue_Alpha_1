# Jira Bulk Import Quick Guide

This project already includes a prepared CSV:

- `docs/project_management/jira_robustness_tasks_import.csv`

## Option A (recommended): CSV import

1. Open your Jira project.
2. Go to backlog/list view.
3. Open the top-right `...` menu and look for an import action (for example `Import issues from CSV`).
4. Upload `jira_robustness_tasks_import.csv`.
5. In field mapping:
   - `Summary -> Summary`
   - `Issue Type -> Issue Type`
   - `Priority -> Priority`
   - `Labels -> Labels`
   - `Description -> Description`
6. Confirm preview, run import.
7. Bulk move/imported items to your sprint columns (`TO DO`, `IN PROGRESS`, etc.).

Note: If CSV import is not visible, your workspace may require admin/project-admin permission for import actions.

## Option B (no import permission): create multiple issues

1. Click `Create`.
2. Use `Create multiple issues` (bulk create).
3. Paste one task summary per line from the CSV.
4. After creation, bulk edit selected issues to set:
   - labels
   - priorities
   - descriptions

## Suggested first sprint cut

- Sprint 1 (P0): first 6 tasks in the CSV.
- Sprint 2 (P1): next 3 tasks.
- Sprint 3 (P2): final configurability task.
