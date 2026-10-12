type Props = { value: number; max: number; tone?: "cobalt" | "verdigris"; label?: string };

export function ProgressBar({ value, max, tone = "cobalt", label }: Props) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div
      className="bar"
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={label}
    >
      <div
        className={`bar__fill${tone === "verdigris" ? " bar__fill--verdigris" : ""}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
