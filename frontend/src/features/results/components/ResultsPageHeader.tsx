type ResultsPageHeaderProps = {
  title: string;
};

export function ResultsPageHeader({ title }: ResultsPageHeaderProps) {
  return (
    <header className="results-page-header">
      <h2>{title}</h2>
    </header>
  );
}
