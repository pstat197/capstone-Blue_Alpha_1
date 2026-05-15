type ValuePillListProps = {
  values: Array<string | number>;
};

export function ValuePillList({ values }: ValuePillListProps) {
  return (
    <div className="value-pill-list">
      {values.map((value) => (
        <span className="value-pill" key={String(value)}>
          {value}
        </span>
      ))}
    </div>
  );
}
