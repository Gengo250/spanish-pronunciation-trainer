type Props = { value: string | number; label: string };

export function Stat({ value, label }: Props) {
  return (
    <div className="stat">
      <div className="stat__value">{value}</div>
      <div className="stat__label label">{label}</div>
    </div>
  );
}
