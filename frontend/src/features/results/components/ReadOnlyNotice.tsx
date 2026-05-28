export function ReadOnlyNotice() {
  return (
    <div className="readonly-notice">
      <span className="readonly-notice__icon" aria-hidden="true" />
      <span>Post-run controls are read-only. These pages explore existing generated outputs and do not change YAML or launch runs.</span>
    </div>
  );
}
