import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { workflowNavItems } from "../../../app/navigation";

type WorkflowScaffoldProps = {
  title: string;
  summary: string;
  children: ReactNode;
  hidePageHeading?: boolean;
  nextHelperText?: string;
  primaryActionLabel?: string;
  primaryActionDisabled?: boolean;
  onPrimaryAction?: () => void;
  hidePrimaryAction?: boolean;
  hideStepper?: boolean;
};

const workflowStepItems = workflowNavItems.filter((item) => item.path !== "/workflow/welcome");

const wizardLabels = [
  "Upload Data",
  "KPI & Revenue Setup",
  "Prior Grid Setup",
  "Structural Settings",
  "Review & Start Run",
];

export function WorkflowScaffold({
  title,
  summary,
  children,
  hidePageHeading = false,
  nextHelperText,
  primaryActionDisabled = false,
  primaryActionLabel,
  onPrimaryAction,
  hidePrimaryAction = false,
  hideStepper = false,
}: WorkflowScaffoldProps) {
  const location = useLocation();
  const currentIndex = workflowNavItems.findIndex((item) => item.path === location.pathname);
  const activeIndex = currentIndex >= 0 ? currentIndex : 0;
  const previousStep = workflowNavItems[activeIndex - 1];
  const nextStep = workflowNavItems[activeIndex + 1];
  const isFinalStep = activeIndex === workflowNavItems.length - 1;
  const actionLabel = primaryActionLabel ?? (isFinalStep ? "Start Run" : "Continue");
  const actionTarget = nextStep?.path;

  const renderPrimaryAction = () => {
    if (onPrimaryAction) {
      return (
        <button
          className="primary-nav-button"
          disabled={primaryActionDisabled}
          onClick={onPrimaryAction}
          type="button"
        >
          {actionLabel}
          <span aria-hidden="true" />
        </button>
      );
    }

    if (actionTarget) {
      if (primaryActionDisabled) {
        return (
          <button className="primary-nav-button" disabled type="button">
            {actionLabel}
            <span aria-hidden="true" />
          </button>
        );
      }

      return (
        <NavLink className="primary-nav-button" to={actionTarget}>
          {actionLabel}
          <span aria-hidden="true" />
        </NavLink>
      );
    }

    return (
      <button className="primary-nav-button" disabled type="button">
        {actionLabel}
        <span aria-hidden="true" />
      </button>
    );
  };

  const renderWizardSteps = () => (
    <nav className="wizard-steps" aria-label="Pre-run workflow steps">
      {workflowStepItems.map((item, index) => {
        const isActive = location.pathname === item.path;
        const stepNumber = index + 1;
        const currentStepIndex = workflowStepItems.findIndex((step) => step.path === location.pathname);
        const isComplete = currentStepIndex >= 0 && index < currentStepIndex;
        const className = [
          "wizard-step",
          isActive ? "wizard-step--active" : "",
          isComplete ? "wizard-step--complete" : "",
        ].filter(Boolean).join(" ");

        return (
          <NavLink aria-current={isActive ? "step" : undefined} className={className} key={item.path} to={item.path}>
            <span>{stepNumber}</span>
            <strong>{wizardLabels[index] ?? item.label}</strong>
          </NavLink>
        );
      })}
    </nav>
  );

  return (
    <article className="workflow-page">
      {!hidePageHeading ? (
        <div className="page-heading">
          <div className="page-heading-copy">
            <h2>{title}</h2>
            <p className="page-summary">{summary}</p>
          </div>
          {hideStepper ? null : renderWizardSteps()}
        </div>
      ) : (
        hideStepper ? null : renderWizardSteps()
      )}
      {children}
      <nav className="workflow-bottom-nav" aria-label="Workflow navigation">
        {previousStep ? (
          <NavLink className="secondary-nav-button" to={previousStep.path}>
            <span aria-hidden="true" />
            Back
          </NavLink>
        ) : (
          <button className="secondary-nav-button" disabled type="button">
            <span aria-hidden="true" />
            Back
          </button>
        )}
        {nextHelperText ? (
          <p className="workflow-next-helper">
            <span>Next screen:</span>
            {nextHelperText}
          </p>
        ) : null}
        {hidePrimaryAction ? null : renderPrimaryAction()}
      </nav>
    </article>
  );
}
