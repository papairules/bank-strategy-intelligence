import type { ReactNode } from "react";

export function MetricCard({
  label,
  value,
  context,
  icon,
}: {
  label: string;
  value: ReactNode;
  context?: string;
  icon: string;
}) {
  return (
    <article className="metric-card">
      <div className="metric-card__top">
        <span>{label}</span>
        <span className="metric-icon" aria-hidden="true">{icon}</span>
      </div>
      <div className="metric-card__value">{value}</div>
      {context && <div className="metric-card__context">{context}</div>}
    </article>
  );
}
